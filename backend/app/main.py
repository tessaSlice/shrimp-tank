from __future__ import annotations

import random
import uuid
import os
import json
from contextvars import ContextVar
from functools import wraps
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .agents import (
    DialogueProviderError,
    active_provider,
    classify_question,
    fact_for,
    player_question_exchange,
    stream_player_question_exchange,
    table_exchange,
)
from .catalog import PITCHES, SHARKS, get_pitch
from .main_types import GameSession
from .spacetime_store import SpacetimeSessionStore
from .store import InMemorySessionStore, SessionStore
from .underwriting import GRADE_RATES, assess, benchmark, offer_is_affordable, score_session


def _cors_origins() -> list[str]:
    local_origins = ["http://localhost:5173", "http://127.0.0.1:5173"]
    configured = os.getenv("FRONTEND_ORIGINS", "")
    production_origins = [origin.strip().rstrip("/") for origin in configured.split(",") if origin.strip()]
    return [*local_origins, *production_origins]


app = FastAPI(title="Shrimp Tank API", version="0.1.0", description="A fictional, rules-based B2B loan negotiation teaching simulator.")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type"],
)


class CreateSession(BaseModel):
    total_pitches: int = Field(default=4, ge=1, le=4)
    difficulty: Literal["easy", "medium", "hard"] = "medium"


class AskQuestion(BaseModel):
    question: str = Field(min_length=2, max_length=400)


class SubmitDecision(BaseModel):
    action: Literal["offer", "pass", "out"]
    amount: int | None = Field(default=None, ge=25_000, le=750_000)
    rate: float | None = Field(default=None, ge=0, le=40)
    royalty: float = Field(default=0, ge=0, le=12)
    term_months: int = Field(default=36, ge=6, le=84)
    secured: bool = False


SESSIONS: SessionStore = SpacetimeSessionStore.from_environment() or InMemorySessionStore()
SESSION_BACKEND = "spacetimedb" if isinstance(SESSIONS, SpacetimeSessionStore) else "in-memory"
CAPITAL_BY_DIFFICULTY = {"easy": 350_000, "medium": 250_000, "hard": 175_000}
TARGET_RATES = GRADE_RATES
ACTIVE_SESSION: ContextVar[GameSession | None] = ContextVar("active_session", default=None)


def _new_message(speaker: str, text: str, kind: str, round_number: int) -> dict:
    return {"id": str(uuid.uuid4()), "speaker": speaker, "text": text, "kind": kind, "round": round_number}


def _start_pitch(session: GameSession) -> None:
    pitch = get_pitch(session.pitch_queue[session.pitch_index])
    session.pitch = pitch
    session.round_number = 1
    session.phase = "investigate"
    session.messages = [_new_message(pitch["founder"], pitch["opening"], "opening", 1)]
    session.disclosures = []
    session.offers = []
    session.human_out = False
    session.question_asked = False
    session.pending_result = None
    session.result = None


def _public_offer(offer: dict) -> dict:
    return {key: value for key, value in offer.items() if key != "internal"}


def _public_state(session: GameSession) -> dict:
    pitch = session.pitch
    public_pitch = {
        "id": pitch["id"],
        "archetype": pitch["archetype"],
        "company": pitch["company"],
        "founder": pitch["founder"],
        "sector": pitch["sector"],
        "ask_amount": pitch["ask_amount"],
        "opening_rate": pitch["opening_rate"],
        "purpose": pitch["purpose"],
        "opening": pitch["opening"],
        "public_revenue": pitch["public_revenue"],
    }
    active_offers = [
        _public_offer(offer)
        for offer in session.offers
        if offer["status"] in ("pending", "accepted")
    ]
    return {
        "id": session.session_id,
        "phase": session.phase,
        "difficulty": session.difficulty,
        "total_pitches": session.total_pitches,
        "pitch_index": session.pitch_index + 1,
        "round": session.round_number,
        "max_rounds": 3,
        "balance": session.balance,
        "starting_capital": session.starting_capital,
        "pitch": public_pitch,
        "messages": session.messages,
        "disclosures": session.disclosures,
        "offers": active_offers,
        "sharks": SHARKS,
        "question_asked": session.question_asked,
        "human_out": session.human_out,
        "result": session.result,
        "scorecard": session.scorecard if session.phase != "pitch_review" else None,
        "ai_mode": active_provider(),
    }


def _deal_candidate(offer: dict, assessment: dict, pitch: dict) -> bool:
    target_rate = assessment["target_rate"]
    if target_rate is None or offer["amount"] < pitch["ask_amount"] * 0.78:
        return False
    if offer["rate"] < target_rate:
        return False
    if assessment["grade"] >= 4 and not offer["secured"]:
        return False
    return True


def _founder_preference(offer: dict, pitch: dict) -> float:
    # Larger funding is helpful; above-ask capital has sharply diminishing value.
    funding = min(1.0, offer["amount"] / pitch["ask_amount"])
    price = max(0.0, offer["rate"] - pitch["opening_rate"])
    royalty_cost = offer["royalty"] * 1.5
    return funding * 100 - price * 2.1 - royalty_cost


def _eligible_shark_offer(session: GameSession, assessment: dict) -> dict | None:
    if session.round_number < 2:
        return None
    already_in = {item["investor_id"] for item in session.offers if item["investor_id"] != "human_user" and item["status"] == "pending"}
    candidates = [shark for shark in SHARKS if shark["id"] not in already_in and assessment["grade"] <= shark["max_grade"]]
    if not candidates:
        return None
    shark = candidates[0] if session.round_number == 2 else candidates[-1]
    amount = min(session.pitch["ask_amount"], shark["capital"])
    if amount < session.pitch["ask_amount"] * 0.78:
        return None
    grade = assessment["grade"]
    rate = (TARGET_RATES[grade] or 0) + (1.25 if shark["id"] == "kevin" else 2.0 if shark["id"] == "lori" else 0.75)
    return {
        "id": str(uuid.uuid4()),
        "investor_id": shark["id"],
        "investor": shark["name"],
        "kind": "shark",
        "amount": amount,
        "rate": round(rate, 2),
        "royalty": 0 if shark["id"] != "mark" else 0.5,
        "term_months": 36,
        "secured": grade >= 3,
        "round": session.round_number,
        "status": "pending",
    }


def _record_shark_offer(session: GameSession, assessment: dict) -> None:
    shark_offer = _eligible_shark_offer(session, assessment)
    if not shark_offer:
        return
    session.offers.append(shark_offer)
    secured = ", secured against equipment" if shark_offer["secured"] else ""
    session.messages.append(_new_message(
        shark_offer["investor"],
        f"I'm interested: ${shark_offer['amount']:,} at {shark_offer['rate']:.2f}%{secured}.",
        "offer",
        session.round_number,
    ))


def _append_ai_table_exchange(session: GameSession, exchange: dict) -> None:
    if exchange["topic"] not in session.disclosures:
        session.disclosures.append(exchange["topic"])
    shark_message = _new_message(exchange["shark_name"], exchange["shark_question"], "shark_question", session.round_number)
    founder_message = _new_message(session.pitch["founder"], exchange["founder_answer"], "answer", session.round_number)
    reaction_message = _new_message(exchange["next_shark_name"], exchange["shark_reaction"], "shark_question", session.round_number)
    shark_message["source"] = founder_message["source"] = reaction_message["source"] = exchange["source"]
    session.messages.extend((shark_message, founder_message, reaction_message))


async def _complete_ai_negotiation(session: GameSession, assessment: dict, benchmark_data: dict) -> None:
    """Let the remaining investors finish the pitch after the player exits."""
    next_round = session.round_number
    if session.question_asked:
        next_round += 1

    planned_exchanges = []
    dialogue_context = list(session.messages)
    for round_number in range(next_round, 4):
        exchange = await table_exchange(session.pitch, dialogue_context, round_number, player_out=True)
        planned_exchanges.append((round_number, exchange))
        dialogue_context.extend((
            {"speaker": exchange["shark_name"], "text": exchange["shark_question"], "kind": "shark_question"},
            {"speaker": session.pitch["founder"], "text": exchange["founder_answer"], "kind": "answer"},
            {"speaker": exchange["next_shark_name"], "text": exchange["shark_reaction"], "kind": "shark_question"},
        ))

    # Apply the state changes only after Grok has generated every remaining round.
    session.human_out = True
    for previous in session.offers:
        if previous["investor_id"] == "human_user" and previous["status"] == "pending":
            previous["status"] = "withdrawn"
    session.messages.append(_new_message(
        "Stage manager",
        "You are out. The remaining investors will continue the discussion and make their own offers.",
        "round",
        session.round_number,
    ))
    if session.question_asked:
        _record_shark_offer(session, assessment)

    for round_number, exchange in planned_exchanges:
        session.round_number = round_number
        if round_number > 1:
            session.messages.append(_new_message(
                "Stage manager",
                f"Round {round_number} of 3. The remaining investors continue without you.",
                "round",
                round_number,
            ))
        _append_ai_table_exchange(session, exchange)
        _record_shark_offer(session, assessment)

    acceptable = [offer for offer in session.offers if offer["status"] == "pending" and _deal_candidate(offer, assessment, session.pitch)]
    winner = max(acceptable, key=lambda offer: _founder_preference(offer, session.pitch)) if acceptable else None
    _finish_pitch(session, assessment, benchmark_data, winner)


def _finish_pitch(session: GameSession, assessment: dict, benchmark_data: dict, winner: dict | None) -> None:
    if winner:
        winner["status"] = "accepted"
        for offer in session.offers:
            if offer is not winner and offer["status"] == "pending":
                offer["status"] = "rejected"
        if winner["investor_id"] == "human_user":
            session.balance -= winner["amount"]
        outcome = "deal"
        winner_id = winner["investor_id"]
    else:
        for offer in session.offers:
            if offer["status"] == "pending":
                offer["status"] = "rejected"
        outcome = "no_deal"
        winner_id = None

    session.pending_result = {
        "outcome": outcome,
        "winner": winner_id,
        "winner_name": winner["investor"] if winner else None,
        "grade": assessment["grade"],
        "risk_label": assessment["label"],
        "message": (
            f"{session.pitch['founder']} accepted {winner['investor']}'s offer: "
            f"${winner['amount']:,} at {winner['rate']:.2f}%" if winner else
            f"{session.pitch['founder']} is leaving without a deal."
        ),
    }
    session.completed.append({
        "pitch_id": session.pitch["id"],
        "company": session.pitch["company"],
        "archetype": session.pitch["archetype"],
        "profile": session.pitch["profile"].copy(),
        "credit_score": session.pitch["profile"]["credit_score"],
        "assessment": assessment,
        "benchmark": benchmark_data,
        "offers": [_public_offer(offer) for offer in session.offers],
        "player_offer": next((offer.copy() for offer in reversed(session.offers) if offer["investor_id"] == "human_user" and offer["status"] in ("accepted", "rejected", "pending")), None),
        "winner": winner_id,
        "decision": outcome,
    })

    if session.pitch_index + 1 >= session.total_pitches:
        session.scorecard = score_session(session.completed, session.starting_capital)
        session.scorecard["projected_ending_capital"] = session.starting_capital + session.scorecard["expected_profit"]
    session.result = None
    session.phase = "pitch_review"
    session.messages.append(_new_message(
        "Stage manager",
        "The round is closed. Review the full conversation and every offer before revealing the founder's decision.",
        "round",
        session.round_number,
    ))


@app.get("/api/health")
async def health() -> dict:
    return {"ok": True, "service": "shrimp-tank", "database": SESSION_BACKEND}


@app.get("/api/config")
async def config() -> dict:
    return {
        "ai_provider": active_provider(),
        "database": SESSION_BACKEND,
    }


@app.post("/api/sessions")
async def create_session(payload: CreateSession) -> dict:
    starting_capital = CAPITAL_BY_DIFFICULTY[payload.difficulty]
    seed = random.SystemRandom()
    pitch_queue = [item["id"] for item in seed.sample(PITCHES, payload.total_pitches)]
    session = GameSession(
        session_id=str(uuid.uuid4()),
        total_pitches=payload.total_pitches,
        difficulty=payload.difficulty,
        starting_capital=starting_capital,
        pitch_queue=pitch_queue,
        balance=starting_capital,
    )
    _start_pitch(session)
    SESSIONS.put(session)
    return _public_state(session)


def _get_session(session_id: str) -> GameSession:
    active = ACTIVE_SESSION.get()
    session = active if active and active.session_id == session_id else SESSIONS.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found; start a new game.")
    return session


def _serialize_session(handler):
    @wraps(handler)
    async def wrapped(session_id: str, *args, **kwargs):
        async with SESSIONS.lock_for(session_id):
            session = _get_session(session_id)
            context_token = ACTIVE_SESSION.set(session)
            try:
                result = await handler(session_id, *args, **kwargs)
                SESSIONS.put(session)
                return result
            finally:
                ACTIVE_SESSION.reset(context_token)
    return wrapped


@app.get("/api/sessions/{session_id}")
async def get_session(session_id: str) -> dict:
    return _public_state(_get_session(session_id))


@app.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str) -> dict:
    async with SESSIONS.lock_for(session_id):
        _get_session(session_id)
        SESSIONS.delete(session_id)
    return {"ok": True}


def _append_question_exchange(session: GameSession, question: str, topic: str | None, exchange: dict) -> None:
    if topic and topic not in session.disclosures:
        session.disclosures.append(topic)
    session.messages.append(_new_message("You", question, "question", session.round_number))
    founder_answer = _new_message(session.pitch["founder"], exchange["founder_answer"], "answer", session.round_number)
    shark_question_message = _new_message(exchange["shark_name"], exchange["shark_question"], "shark_question", session.round_number)
    founder_followup = _new_message(session.pitch["founder"], exchange["founder_followup"], "answer", session.round_number)
    shark_reaction = _new_message(exchange["next_shark_name"], exchange["shark_reaction"], "shark_question", session.round_number)
    for message in (founder_answer, shark_question_message, founder_followup, shark_reaction):
        message["source"] = exchange["source"]
    session.messages.extend((founder_answer, shark_question_message, founder_followup, shark_reaction))
    if exchange["topic"] not in session.disclosures:
        session.disclosures.append(exchange["topic"])
    session.question_asked = True


def _sse(event: str, payload: dict) -> str:
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event}\ndata: {data}\n\n"


@app.post("/api/sessions/{session_id}/question")
@_serialize_session
async def ask_question(session_id: str, payload: AskQuestion) -> dict:
    session = _get_session(session_id)
    if session.phase != "investigate":
        raise HTTPException(status_code=409, detail="Questions are only available during the investigation phase.")
    if session.question_asked:
        raise HTTPException(status_code=409, detail="You have already asked a question this round. Submit an offer or pass to continue.")
    question = payload.question.strip()
    if len(question) < 2:
        raise HTTPException(status_code=422, detail="Ask a little more than one character.")

    topic = classify_question(question)
    fact = fact_for(session.pitch, topic)
    try:
        exchange = await player_question_exchange(
            session.pitch,
            question,
            fact,
            session.messages,
            session.round_number,
        )
    except DialogueProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    _append_question_exchange(session, question, topic, exchange)
    return _public_state(session)


@app.post("/api/sessions/{session_id}/question/stream")
async def ask_question_stream(session_id: str, payload: AskQuestion):
    # Validate before sending response headers so ordinary game-state errors remain HTTP errors.
    session = _get_session(session_id)
    if session.phase != "investigate":
        raise HTTPException(status_code=409, detail="Questions are only available during the investigation phase.")
    if session.question_asked:
        raise HTTPException(status_code=409, detail="You have already asked a question this round. Submit an offer or pass to continue.")
    question = payload.question.strip()
    if len(question) < 2:
        raise HTTPException(status_code=422, detail="Ask a little more than one character.")

    async def event_stream():
        async with SESSIONS.lock_for(session_id):
            active = _get_session(session_id)
            if active.phase != "investigate" or active.question_asked:
                yield _sse("error", {"detail": "This round has already changed. Refresh the game and try again."})
                return

            yield _sse("message_start", {
                "field": "player_question",
                "speaker": "You",
                "kind": "question",
                "round": active.round_number,
            })
            yield _sse("delta", {"field": "player_question", "text": question})
            yield _sse("progress", {"message": "The founder and investors are preparing their responses…"})
            topic = classify_question(question)
            fact = fact_for(active.pitch, topic)
            exchange = None
            try:
                async for item in stream_player_question_exchange(
                    active.pitch,
                    question,
                    fact,
                    active.messages,
                    active.round_number,
                ):
                    if item["type"] == "start":
                        yield _sse("message_start", {
                            "field": item["field"],
                            "speaker": item["speaker"],
                            "kind": item["kind"],
                            "round": active.round_number,
                        })
                    elif item["type"] == "delta":
                        yield _sse("delta", {"field": item["field"], "text": item["text"]})
                    elif item["type"] == "result":
                        exchange = item["value"]
                if exchange is None:
                    raise DialogueProviderError("Grok ended the stream before completing its response. Please retry.")
                _append_question_exchange(active, question, topic, exchange)
                SESSIONS.put(active)
                yield _sse("complete", _public_state(active))
            except DialogueProviderError as exc:
                yield _sse("error", {"detail": str(exc)})
            except Exception:
                # Do not send implementation details or credentials through the event stream.
                yield _sse("error", {"detail": "The game could not save this turn. Please retry."})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )


@app.post("/api/sessions/{session_id}/decision")
@_serialize_session
async def submit_decision(session_id: str, payload: SubmitDecision) -> dict:
    session = _get_session(session_id)
    if session.phase != "investigate":
        raise HTTPException(status_code=409, detail="This pitch is already resolved.")
    assessment = assess(session.pitch["profile"], session.pitch["ask_amount"])
    benchmark_data = benchmark(assessment, session.pitch["profile"], session.pitch["ask_amount"])

    if payload.action == "offer":
        if session.human_out:
            raise HTTPException(status_code=409, detail="You are out on this pitch and cannot make another offer.")
        if payload.amount is None or payload.rate is None:
            raise HTTPException(status_code=422, detail="A loan offer needs an amount and annual interest rate.")
        offer = {
            "id": str(uuid.uuid4()),
            "investor_id": "human_user",
            "investor": "You",
            "kind": "human",
            "amount": payload.amount,
            "rate": payload.rate,
            "royalty": payload.royalty,
            "term_months": payload.term_months,
            "secured": payload.secured,
            "round": session.round_number,
            "status": "pending",
        }
        if not offer_is_affordable(offer, session.pitch["ask_amount"]):
            raise HTTPException(status_code=422, detail="Check the amount, rate, and royalty. Amount must be at least 78% of the ask; rate is capped at 40%.")
        if payload.amount > session.balance:
            raise HTTPException(status_code=422, detail=f"Your remaining capital is ${session.balance:,}.")
        for previous in session.offers:
            if previous["investor_id"] == "human_user" and previous["status"] == "pending":
                previous["status"] = "withdrawn"
        session.offers.append(offer)
    elif payload.action == "out":
        try:
            await _complete_ai_negotiation(session, assessment, benchmark_data)
        except DialogueProviderError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return _public_state(session)
    elif payload.action == "pass":
        try:
            exchange = await table_exchange(session.pitch, session.messages, session.round_number)
        except DialogueProviderError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        _append_ai_table_exchange(session, exchange)

    _record_shark_offer(session, assessment)

    acceptable = [offer for offer in session.offers if offer["status"] == "pending" and _deal_candidate(offer, assessment, session.pitch)]
    winner = max(acceptable, key=lambda offer: _founder_preference(offer, session.pitch)) if acceptable else None
    if winner:
        _finish_pitch(session, assessment, benchmark_data, winner)
        return _public_state(session)

    if session.round_number >= 3:
        _finish_pitch(session, assessment, benchmark_data, None)
        return _public_state(session)

    session.round_number += 1
    session.question_asked = False
    session.messages.append(_new_message("Stage manager", "The table is open. Ask one more question before your next move.", "round", session.round_number))
    return _public_state(session)


@app.post("/api/sessions/{session_id}/next")
@_serialize_session
async def next_pitch(session_id: str) -> dict:
    session = _get_session(session_id)
    if session.phase != "pitch_result":
        raise HTTPException(status_code=409, detail="There is no completed pitch waiting to advance.")
    session.pitch_index += 1
    _start_pitch(session)
    return _public_state(session)


@app.post("/api/sessions/{session_id}/reveal")
@_serialize_session
async def reveal_decision(session_id: str) -> dict:
    session = _get_session(session_id)
    if session.phase != "pitch_review" or not session.pending_result:
        raise HTTPException(status_code=409, detail="There is no founder decision ready to reveal.")
    session.result = session.pending_result
    session.pending_result = None
    session.phase = "pitch_result"
    return _public_state(session)


@app.get("/api/sessions/{session_id}/scorecard")
async def get_scorecard(session_id: str) -> dict:
    session = _get_session(session_id)
    if session.phase != "complete" or not session.scorecard:
        raise HTTPException(status_code=409, detail="The scorecard is available after the final pitch.")
    return session.scorecard
