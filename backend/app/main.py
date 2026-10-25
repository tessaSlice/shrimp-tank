from __future__ import annotations

import random
import uuid
import os
import json
from contextvars import ContextVar
from functools import wraps
from typing import Literal

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .agents import (
    DialogueProviderError,
    active_provider,
    classify_question,
    fact_for,
    founder_counters,
    player_question_exchange,
    stream_player_question_exchange,
    table_exchange,
)
from .catalog import PROFILES, SHARKS, get_pitch
from .main_types import GameSession
from .portfolio_agent import create_simulated_portfolios, refresh_simulated_portfolios
from .room_hub import ROOM_HUB
from .spacetime_store import SpacetimeSessionStore
from .store import InMemorySessionStore, SessionStore
from .underwriting import GRADE_RATES, assess, benchmark, offer_is_affordable, offer_matches_request, score_session


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
    allow_headers=["Content-Type", "X-Room-Client-ID"],
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
# Three rounds with no offer at all, and the founder walks away.
EMPTY_TABLE_ROUND_LIMIT = 3
# After an offer exists, one later round with no newer offer closes the pitch.
QUIET_ROUND_LIMIT = 1
# Safety stop for the exit fast-forward. Each shark originates one bid and revises it at most once.
MAX_TABLE_ROUND = 24
ACTIVE_SESSION: ContextVar[GameSession | None] = ContextVar("active_session", default=None)


def _new_message(speaker: str, text: str, kind: str, round_number: int) -> dict:
    return {"id": str(uuid.uuid4()), "speaker": speaker, "text": text, "kind": kind, "round": round_number}


def _start_pitch(session: GameSession) -> None:
    previous_player_index = next(
        (index for index, player in enumerate(session.players) if player["id"] == session.current_player_id),
        -1,
    )
    pitch = get_pitch(session.pitch_queue[session.pitch_index])
    session.pitch = pitch
    session.round_number = 1
    session.phase = "investigate"
    session.messages = [_new_message(pitch["founder"], pitch["opening"], "opening", 1)]
    session.disclosures = []
    session.offers = []
    session.human_out = False
    session.question_asked = False
    for player in session.players:
        player["out"] = False
    active_players = [player for player in session.players if not player.get("out")]
    if active_players:
        if previous_player_index >= 0:
            for offset in range(1, len(session.players) + 1):
                candidate = session.players[(previous_player_index + offset) % len(session.players)]
                if not candidate.get("out"):
                    session.current_player_id = candidate["id"]
                    break
        else:
            session.current_player_id = active_players[0]["id"]
    session.last_new_offer_round = 0
    session.pending_result = None
    session.result = None


def _player_for_client(session: GameSession, client_id: str | None) -> tuple[dict, bool]:
    """Return or create this browser's independent investor seat."""
    if not session.players:
        player_id = str(uuid.uuid4()) if client_id else "human_user"
        player = {
            "id": player_id,
            "client_id": client_id,
            "name": "You" if not client_id else "Player 1",
            "is_host": True,
            "joined_pitch_index": 0,
            "balance": session.balance or session.starting_capital,
            "starting_capital": session.starting_capital,
            "out": False,
        }
        session.players.append(player)
        session.current_player_id = player_id
        return player, True
    if client_id:
        existing = next((player for player in session.players if player.get("client_id") == client_id), None)
        if existing:
            if "joined_pitch_index" not in existing:
                existing["joined_pitch_index"] = 0
                changed = True
            else:
                changed = False
            if "is_host" not in existing:
                existing["is_host"] = session.players.index(existing) == 0
                changed = True
            return existing, changed
        # Old persisted sessions predate player identities. Bind their original
        # seat to the first browser that resumes it.
        legacy = next((player for player in session.players if player.get("client_id") is None), None)
        if legacy:
            legacy["client_id"] = client_id
            legacy.setdefault("is_host", session.players.index(legacy) == 0)
            legacy.setdefault("joined_pitch_index", 0)
            return legacy, True
        player_id = str(uuid.uuid4())
        player = {
            "id": player_id,
            "client_id": client_id,
            "name": f"Player {len(session.players) + 1}",
            "is_host": False,
            "joined_pitch_index": session.pitch_index if session.phase == "investigate" else session.pitch_index + 1,
            "balance": session.starting_capital,
            "starting_capital": session.starting_capital,
            "out": False,
        }
        session.players.append(player)
        return player, True
    legacy = next((player for player in session.players if player["id"] == "human_user"), session.players[0])
    if "is_host" not in legacy:
        legacy["is_host"] = session.players.index(legacy) == 0
        return legacy, True
    return legacy, False


def _player_by_id(session: GameSession, player_id: str | None) -> dict | None:
    return next((player for player in session.players if player["id"] == player_id), None)


def _require_player_turn(session: GameSession, client_id: str | None) -> dict:
    player, _ = _player_for_client(session, client_id)
    if player.get("out"):
        raise HTTPException(status_code=409, detail="You are out on this pitch and cannot take another action.")
    if session.current_player_id != player["id"]:
        current = _player_by_id(session, session.current_player_id)
        name = current["name"] if current else "another investor"
        raise HTTPException(status_code=409, detail=f"It is {name}'s turn. Wait for your turn before acting.")
    return player


def _public_offer(offer: dict) -> dict:
    return {key: value for key, value in offer.items() if key != "internal"}


def _accepted_offer_message(founder: str, offer: dict, viewer_id: str | None = None) -> str:
    player_id = offer.get("player_id", offer["investor_id"])
    description = (
        "your offer"
        if player_id == "human_user" or (viewer_id is not None and player_id == viewer_id)
        else f"{offer['investor']}'s offer"
    )
    return f"{founder} accepted {description}: ${offer['amount']:,} at {offer['rate']:.2f}%"


def _public_portfolio(portfolio: dict) -> dict:
    recommendation = portfolio.get("recommendation") or {}
    return {
        "investor_id": portfolio.get("investor_id"),
        "investor": portfolio.get("investor"),
        "strategy": portfolio.get("strategy"),
        "starting_value_usd": portfolio.get("starting_value_usd", 0),
        "cash_usd": portfolio.get("cash_usd", 0),
        "total_value_usd": portfolio.get("total_value_usd", 0),
        "return_pct": portfolio.get("return_pct", 0),
        "cash_posture": portfolio.get("cash_posture", "unknown"),
        "positions": [
            {
                "asset": position.get("asset"),
                "market_value_usd": position.get("market_value_usd", 0),
                "change_24h_pct": position.get("change_24h_pct"),
            }
            for position in portfolio.get("positions", [])
        ],
        "market_mode": portfolio.get("market_mode", "unavailable"),
        "updated_at": portfolio.get("updated_at"),
        "recommendation": {
            key: recommendation.get(key)
            for key in ("action", "asset", "amount_usd", "signal_pct", "summary", "status", "as_of")
        },
    }


def _public_state(session: GameSession, client_id: str | None = None) -> dict:
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
    viewer = next((player for player in session.players if client_id and player.get("client_id") == client_id), None)
    if viewer is None and client_id is None:
        viewer = _player_by_id(session, "human_user") or (session.players[0] if session.players else None)
    result = session.result
    if result and result.get("outcome") == "deal":
        accepted_offer = next((
            offer for offer in session.offers
            if offer["status"] == "accepted" and offer["investor_id"] == result.get("winner")
        ), None)
        if accepted_offer:
            # Reformat saved results too; their stored wording may predate a copy fix.
            result = {
                **result,
                "message": _accepted_offer_message(
                    pitch["founder"], accepted_offer, viewer["id"] if viewer else None,
                ),
            }
    current_player = _player_by_id(session, session.current_player_id)
    public_players = [
        {
            "id": player["id"],
            "name": player["name"],
            "is_host": bool(player.get("is_host")),
            "out": bool(player.get("out")),
            **({
                "balance": player["balance"],
                "starting_capital": player["starting_capital"],
                "scorecard": session.player_scorecards.get(player["id"]) if session.phase != "pitch_review" else None,
            } if viewer and player["id"] == viewer["id"] else {}),
        }
        for player in session.players
    ]
    viewer_scorecard = (
        session.player_scorecards.get(viewer["id"])
        if viewer and session.player_scorecards
        else session.scorecard if client_id is None else None
    )
    return {
        "id": session.session_id,
        "phase": session.phase,
        "difficulty": session.difficulty,
        "total_pitches": session.total_pitches,
        "pitch_index": session.pitch_index + 1,
        "round": session.round_number,
        "quiet_rounds": _displayed_quiet_rounds(session),
        "quiet_round_limit": _active_quiet_limit(session.last_new_offer_round),
        "balance": viewer["balance"] if viewer else session.balance if client_id is None else None,
        "starting_capital": viewer["starting_capital"] if viewer else session.starting_capital if client_id is None else None,
        "players": public_players,
        "self_player_id": viewer["id"] if viewer else None,
        "current_player_id": session.current_player_id,
        "current_player_name": current_player["name"] if current_player else None,
        "is_my_turn": bool(viewer and current_player and viewer["id"] == current_player["id"] and not viewer.get("out")),
        "pitch": public_pitch,
        "messages": session.messages,
        "disclosures": session.disclosures,
        "offers": active_offers,
        "sharks": SHARKS,
        "investor_portfolios": [_public_portfolio(portfolio) for portfolio in session.investor_portfolios],
        "question_asked": session.question_asked,
        "human_out": bool(viewer.get("out")) if viewer else session.human_out if client_id is None else False,
        "immediate_acceptance": bool((session.pending_result or session.result or {}).get("reason") == "matched_request"),
        "result": result,
        "scorecard": viewer_scorecard if session.phase != "pitch_review" else None,
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


def _active_quiet_limit(last_new_offer_round: int) -> int:
    """No offer at all waits three rounds. After an offer, one quiet round closes the pitch."""
    if last_new_offer_round:
        return QUIET_ROUND_LIMIT
    return EMPTY_TABLE_ROUND_LIMIT


def _quiet_limit_reached(round_number: int, last_new_offer_round: int) -> bool:
    return round_number - last_new_offer_round >= _active_quiet_limit(last_new_offer_round)


def _completed_quiet_rounds(session: GameSession) -> int:
    """Finished rounds since the last new offer, not counting the round still in progress."""
    if session.last_new_offer_round >= session.round_number:
        return 0
    return max(0, session.round_number - session.last_new_offer_round - 1)


def _displayed_quiet_rounds(session: GameSession) -> int:
    limit = _active_quiet_limit(session.last_new_offer_round)
    if session.phase != "investigate":
        return min(limit, max(0, session.round_number - session.last_new_offer_round))
    return _completed_quiet_rounds(session)


def _note_new_offers(session: GameSession, before_ids: set[str]) -> None:
    created = [
        offer for offer in session.offers
        if offer["id"] not in before_ids and offer["status"] == "pending"
    ]
    if created:
        session.last_new_offer_round = session.round_number


def _next_round_text(session: GameSession) -> str:
    opening = f"Round {session.round_number}."
    if session.last_new_offer_round:
        return (
            f"{opening} A new offer reset the clock. "
            "One round without a new offer will make the founder accept a qualifying offer or walk away."
        )
    done = _completed_quiet_rounds(session)
    if done <= 1:
        return f"{opening} One round has passed with no offer."
    return (
        f"{opening} Two rounds have passed with no offer. "
        "If this round also has none, the founder will walk away."
    )


def _shark_offer_for(round_number: int, offers: list[dict], assessment: dict, pitch: dict) -> dict | None:
    if round_number < 2:
        return None
    already_in = {
        item["investor_id"]
        for item in offers
        if item.get("kind") == "shark" and item["status"] == "pending"
    }
    candidates = [shark for shark in SHARKS if shark["id"] not in already_in and assessment["grade"] <= shark["max_grade"]]
    if not candidates:
        return None
    # Round 2 takes the first eligible investor. Later rounds take the last one still waiting.
    shark = candidates[0] if round_number == 2 else candidates[-1]
    amount = min(pitch["ask_amount"], shark["capital"])
    if amount < pitch["ask_amount"] * 0.78:
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
        "round": round_number,
        "status": "pending",
        "concessions": 0,
    }


def _player_offer_text(offer: dict) -> str:
    secured = ", secured" if offer["secured"] else ""
    royalty = f" plus {offer['royalty']:.2f}% revenue share" if offer["royalty"] else ""
    return (
        f"I'll offer ${offer['amount']:,} at {offer['rate']:.2f}% "
        f"for {offer['term_months']} months{royalty}{secured}."
    )


def _append_shark_offer(session: GameSession, shark_offer: dict) -> None:
    session.offers.append(shark_offer)
    secured = ", secured against equipment" if shark_offer["secured"] else ""
    session.messages.append(_new_message(
        shark_offer["investor"],
        f"I'm interested: ${shark_offer['amount']:,} at {shark_offer['rate']:.2f}%{secured}.",
        "offer",
        session.round_number,
    ))


def _append_counters(session: GameSession, counters: list[dict]) -> None:
    for counter in counters:
        message = _new_message(session.pitch["founder"], counter["text"], "counter", session.round_number)
        message["source"] = counter["source"]
        session.messages.append(message)


def _latest_pending_sharks(offers: list[dict]) -> list[dict]:
    latest = {
        offer["investor_id"]: offer
        for offer in offers
        if offer.get("status") == "pending" and offer.get("kind") == "shark"
    }
    return [latest[shark["id"]] for shark in SHARKS if shark["id"] in latest]


def _shark_counter_replies(
    offers: list[dict],
    counters: list[dict],
    pitch: dict,
    assessment: dict,
    round_number: int,
) -> list[dict]:
    """Decide each countered shark's reply. A move replaces the pending bid once."""
    countered = {counter["investor_id"] for counter in counters}
    replies = []
    for offer in _latest_pending_sharks(offers):
        if offer["investor_id"] not in countered:
            continue
        shark = next(item for item in SHARKS if item["id"] == offer["investor_id"])
        policy = shark["ai_profile"]["counter_response"]
        rate = float(offer["rate"])
        royalty = float(offer["royalty"])
        target = assessment.get("target_rate")
        gap = rate - float(pitch["opening_rate"])
        can_consider = (
            int(offer.get("concessions") or 0) < 1
            and target is not None
            and gap <= float(policy["max_gap"])
        )
        new_rate = rate
        new_royalty = royalty
        if can_consider:
            candidate_rate = round(rate - float(policy["rate_cut"]), 2)
            # Stay at or above the grade target. Never raise a rate to reach that floor.
            if candidate_rate >= float(target):
                new_rate = candidate_rate
            new_royalty = round(max(0.0, royalty - float(policy["royalty_cut"])), 2)
        moved = new_rate != rate or new_royalty != royalty
        if moved and new_royalty != royalty and policy.get("budge_royalty"):
            text = policy["budge_royalty"].format(rate=new_rate, royalty=new_royalty)
        elif moved:
            text = policy["budge"].format(rate=new_rate, royalty=new_royalty)
        else:
            text = policy["hold"]
        replacement = None
        if moved:
            replacement = {
                "id": str(uuid.uuid4()),
                "investor_id": offer["investor_id"],
                "investor": offer["investor"],
                "kind": "shark",
                "amount": offer["amount"],
                "rate": new_rate,
                "royalty": new_royalty,
                "term_months": offer["term_months"],
                "secured": offer["secured"],
                "round": round_number,
                "status": "pending",
                "concessions": int(offer.get("concessions") or 0) + 1,
            }
        replies.append({
            "investor_id": offer["investor_id"],
            "investor": offer["investor"],
            "offer_id": offer["id"],
            "text": text,
            "source": "offline",
            "replacement": replacement,
        })
    return replies


def _install_revisions(offers: list[dict], replies: list[dict]) -> bool:
    """Withdraw a bid that moved and append its replacement. Returns whether any moved."""
    moved = False
    for reply in replies:
        replacement = reply["replacement"]
        if replacement is None:
            continue
        for offer in offers:
            if offer["id"] == reply["offer_id"] and offer["status"] == "pending":
                offer["status"] = "withdrawn"
                break
        offers.append(replacement)
        moved = True
    return moved


def _append_shark_replies(session: GameSession, replies: list[dict]) -> None:
    _install_revisions(session.offers, replies)
    for reply in replies:
        message = _new_message(reply["investor"], reply["text"], "reply", session.round_number)
        message["source"] = reply["source"]
        session.messages.append(message)


def _append_ai_table_exchange(session: GameSession, exchange: dict) -> None:
    if exchange["topic"] not in session.disclosures:
        session.disclosures.append(exchange["topic"])
    if exchange.get("founder_offer_reply"):
        reply = _new_message(session.pitch["founder"], exchange["founder_offer_reply"], "counter", session.round_number)
        reply["source"] = exchange.get("founder_offer_source", exchange["source"])
        session.messages.append(reply)
    shark_message = _new_message(exchange["shark_name"], exchange["shark_question"], "shark_question", session.round_number)
    founder_message = _new_message(session.pitch["founder"], exchange["founder_answer"], "answer", session.round_number)
    reaction_message = _new_message(exchange["next_shark_name"], exchange["shark_reaction"], "shark_question", session.round_number)
    shark_message["source"] = founder_message["source"] = reaction_message["source"] = exchange["source"]
    session.messages.extend((shark_message, founder_message, reaction_message))


def _choose_winner(offers: list[dict], assessment: dict, pitch: dict) -> dict | None:
    pending = [offer for offer in offers if offer["status"] == "pending"]
    eligible = [offer for offer in pending if _deal_candidate(offer, assessment, pitch)]
    if not eligible:
        return None
    return max(eligible, key=lambda offer: _founder_preference(offer, pitch))


def _close_for_quiet_table(session: GameSession, assessment: dict, benchmark_data: dict) -> None:
    pending = [offer for offer in session.offers if offer["status"] == "pending"]
    if session.last_new_offer_round and pending:
        notice = (
            "One round has passed with no new offer. "
            "The founder will accept a qualifying offer or walk away."
        )
    elif session.last_new_offer_round:
        notice = "One round has passed with no new offer, and the table has no offer left to accept."
    else:
        notice = "Three rounds have passed with no offer, and the table has no offer left to accept."
    session.messages.append(_new_message("Stage manager", notice, "round", session.round_number))
    winner = _choose_winner(session.offers, assessment, session.pitch)
    _finish_pitch(session, assessment, benchmark_data, winner)


def _advance_round(session: GameSession) -> None:
    session.round_number += 1
    session.question_asked = False
    active_players = [player for player in session.players if not player.get("out")]
    if active_players:
        current_index = next((i for i, player in enumerate(session.players) if player["id"] == session.current_player_id), -1)
        for offset in range(1, len(session.players) + 1):
            candidate = session.players[(current_index + offset) % len(session.players)]
            if not candidate.get("out"):
                session.current_player_id = candidate["id"]
                break
    session.messages.append(_new_message("Stage manager", _next_round_text(session), "round", session.round_number))


def _messages_with_exchange(messages: list[dict], exchange: dict, founder: str) -> list[dict]:
    return [
        *messages,
        *([{"speaker": founder, "text": exchange["founder_offer_reply"], "kind": "counter"}]
          if exchange.get("founder_offer_reply") else []),
        {"speaker": exchange["shark_name"], "text": exchange["shark_question"], "kind": "shark_question"},
        {"speaker": founder, "text": exchange["founder_answer"], "kind": "answer"},
        {"speaker": exchange["next_shark_name"], "text": exchange["shark_reaction"], "kind": "shark_question"},
    ]


async def _round_follow_up(
    session: GameSession,
    assessment: dict,
    offers: list[dict],
    round_number: int,
    messages: list[dict],
    responded_offer_id: str | None = None,
) -> tuple[dict | None, list[dict]]:
    """Predict this round's shark bid and founder counters without mutating the session."""
    shark_offer = _shark_offer_for(round_number, offers, assessment, session.pitch)
    projected = [*offers, shark_offer] if shark_offer else list(offers)
    counters = await founder_counters(
        session.pitch, [offer for offer in projected if offer["id"] != responded_offer_id], messages,
    )
    return shark_offer, counters


def _settle_round(
    session: GameSession,
    assessment: dict,
    benchmark_data: dict,
    before_ids: set[str],
    shark_offer: dict | None,
    counters: list[dict],
) -> None:
    if shark_offer:
        _append_shark_offer(session, shark_offer)
    _note_new_offers(session, before_ids)
    _append_counters(session, counters)
    replies = _shark_counter_replies(
        session.offers, counters, session.pitch, assessment, session.round_number,
    )
    revision_ids = {offer["id"] for offer in session.offers}
    _append_shark_replies(session, replies)
    _note_new_offers(session, revision_ids)
    if _quiet_limit_reached(session.round_number, session.last_new_offer_round):
        _close_for_quiet_table(session, assessment, benchmark_data)
        return
    _advance_round(session)


async def _complete_ai_negotiation(session: GameSession, assessment: dict, benchmark_data: dict) -> None:
    """Let the remaining investors continue until the quiet-offer rule closes the pitch."""
    left_during = session.round_number
    sim_offers = [dict(offer) for offer in session.offers]
    for offer in sim_offers:
        if offer.get("kind") == "human" and offer["status"] == "pending":
            offer["status"] = "withdrawn"
    sim_last = session.last_new_offer_round
    dialogue_context = list(session.messages)
    planned: list[dict] = []

    async def plan_round(round_number: int, include_exchange: bool) -> bool:
        nonlocal sim_last, dialogue_context
        exchange = None
        if include_exchange:
            exchange = await table_exchange(
                session.pitch, dialogue_context, round_number, player_out=True,
                investor_portfolios=session.investor_portfolios,
            )
            dialogue_context = [
                *dialogue_context,
                {"speaker": exchange["shark_name"], "text": exchange["shark_question"], "kind": "shark_question"},
                {"speaker": session.pitch["founder"], "text": exchange["founder_answer"], "kind": "answer"},
                {"speaker": exchange["next_shark_name"], "text": exchange["shark_reaction"], "kind": "shark_question"},
            ]
        shark_offer = _shark_offer_for(round_number, sim_offers, assessment, session.pitch)
        projected = [*sim_offers, shark_offer] if shark_offer else list(sim_offers)
        counters = await founder_counters(session.pitch, projected, dialogue_context)
        if shark_offer:
            # Copy so a simulated revision does not withdraw the offer before it is recorded.
            sim_offers.append(dict(shark_offer))
            sim_last = round_number
        replies = _shark_counter_replies(
            sim_offers, counters, session.pitch, assessment, round_number,
        )
        if _install_revisions(sim_offers, replies):
            sim_last = round_number
        dialogue_context = [
            *dialogue_context,
            *({"speaker": session.pitch["founder"], "text": counter["text"], "kind": "counter"} for counter in counters),
            *({"speaker": reply["investor"], "text": reply["text"], "kind": "reply"} for reply in replies),
        ]
        forced = _quiet_limit_reached(round_number, sim_last)
        planned.append({
            "round_number": round_number,
            "exchange": exchange,
            "shark_offer": shark_offer,
            "counters": counters,
            "replies": replies,
            "force": forced,
        })
        return forced

    forced = False
    if session.question_asked:
        # The question already supplied this round's table talk. Still record a shark bid and counters.
        forced = await plan_round(session.round_number, include_exchange=False)
        next_round = session.round_number + 1
    else:
        next_round = session.round_number

    round_number = next_round
    while not forced and round_number <= MAX_TABLE_ROUND:
        forced = await plan_round(round_number, include_exchange=True)
        round_number += 1
    if planned and not planned[-1]["force"]:
        planned[-1]["force"] = True

    # Apply the state changes only after every remaining round has been generated.
    session.human_out = True
    for previous in session.offers:
        if previous.get("kind") == "human" and previous["status"] == "pending":
            previous["status"] = "withdrawn"
    session.messages.append(_new_message(
        "Stage manager",
        "All human investors are out. The remaining sharks will continue the discussion and make their own offers.",
        "round",
        session.round_number,
    ))
    for step in planned:
        session.round_number = step["round_number"]
        if step["round_number"] != left_during:
            session.messages.append(_new_message(
                "Stage manager",
                f"Round {step['round_number']}. The remaining investors continue without you.",
                "round",
                step["round_number"],
            ))
        before_ids = {offer["id"] for offer in session.offers}
        if step["exchange"]:
            _append_ai_table_exchange(session, step["exchange"])
        if step["shark_offer"]:
            _append_shark_offer(session, step["shark_offer"])
        _note_new_offers(session, before_ids)
        _append_counters(session, step["counters"])
        revision_ids = {offer["id"] for offer in session.offers}
        _append_shark_replies(session, step["replies"])
        _note_new_offers(session, revision_ids)
        if step["force"]:
            _close_for_quiet_table(session, assessment, benchmark_data)
            return
    _close_for_quiet_table(session, assessment, benchmark_data)


def _scorecards_for_session(session: GameSession) -> None:
    session.player_scorecards = {}
    for player in session.players:
        joined_index = player.get("joined_pitch_index", 0)
        participated = [
            pitch for pitch in session.completed
            if player["id"] in pitch.get("player_ids", [])
            or ("player_ids" not in pitch and pitch.get("pitch_index", 0) >= joined_index)
        ]
        if participated:
            scorecard = score_session(
                participated,
                player["starting_capital"],
                player_id=player["id"],
            )
        else:
            scorecard = {
                "overall_score": 0,
                "decision_accuracy": 0,
                "expected_profit": 0,
                "deals_funded": 0,
                "starting_capital": player["starting_capital"],
                "pitches": [],
                "notice": "No completed pitches were played from this seat.",
            }
        scorecard["projected_ending_capital"] = player["starting_capital"] + scorecard["expected_profit"]
        session.player_scorecards[player["id"]] = scorecard
    session.scorecard = session.player_scorecards.get("human_user") or next(iter(session.player_scorecards.values()), None)


def _finish_pitch(
    session: GameSession, assessment: dict, benchmark_data: dict, winner: dict | None,
    *, reason: str = "quiet_table",
) -> None:
    if winner:
        winner["status"] = "accepted"
        for offer in session.offers:
            if offer is not winner and offer["status"] == "pending":
                offer["status"] = "rejected"
        winning_player_id = winner.get("player_id")
        if winner.get("kind") == "human":
            winning_player = _player_by_id(session, winning_player_id or winner["investor_id"])
            if winning_player:
                winning_player["balance"] -= winner["amount"]
                if winning_player["id"] == "human_user":
                    session.balance = winning_player["balance"]
        outcome = "deal"
        winner_id = winner["investor_id"]
    else:
        for offer in session.offers:
            if offer["status"] == "pending":
                offer["status"] = "rejected"
        outcome = "no_deal"
        winner_id = None

    session.pending_result = {
        "reason": reason,
        "outcome": outcome,
        "winner": winner_id,
        "winner_name": winner["investor"] if winner else None,
        "grade": assessment["grade"],
        "risk_label": assessment["label"],
        "message": (
            _accepted_offer_message(session.pitch["founder"], winner) if winner else
            f"{session.pitch['founder']} is leaving without a deal."
        ),
    }
    player_offers = {
        player["id"]: next((
            offer.copy() for offer in reversed(session.offers)
            if offer.get("player_id", offer.get("investor_id")) == player["id"]
            and offer.get("kind") == "human"
            and offer["status"] in ("accepted", "rejected", "pending")
        ), None)
        for player in session.players
    }
    player_ids = list(dict.fromkeys(
        message["player_id"] for message in session.messages if message.get("player_id")
    ))
    session.completed.append({
        "pitch_index": session.pitch_index,
        "pitch_id": session.pitch["id"],
        "company": session.pitch["company"],
        "archetype": session.pitch["archetype"],
        "profile": session.pitch["profile"].copy(),
        "credit_score": session.pitch["profile"]["credit_score"],
        "assessment": assessment,
        "benchmark": benchmark_data,
        "offers": [_public_offer(offer) for offer in session.offers],
        "player_offer": next((offer.copy() for offer in reversed(session.offers) if offer["investor_id"] == "human_user" and offer["status"] in ("accepted", "rejected", "pending")), None),
        "player_offers": player_offers,
        "player_ids": player_ids,
        "winner": winner_id,
        "winner_name": winner["investor"] if winner else None,
        "decision": outcome,
    })

    if session.pitch_index + 1 >= session.total_pitches:
        _scorecards_for_session(session)
    session.result = None
    session.phase = "pitch_review"
    session.messages.append(_new_message(
        "Stage manager",
        "The founder accepted the matching offer. The pitch is closed; the full conversation remains available for review."
        if reason == "matched_request" else
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
async def create_session(payload: CreateSession, request: Request) -> dict:
    starting_capital = CAPITAL_BY_DIFFICULTY[payload.difficulty]
    seed = random.SystemRandom()
    pitch_queue = [item["id"] for item in seed.sample(PROFILES, payload.total_pitches)]
    session = GameSession(
        session_id=str(uuid.uuid4()),
        total_pitches=payload.total_pitches,
        difficulty=payload.difficulty,
        starting_capital=starting_capital,
        pitch_queue=pitch_queue,
        balance=starting_capital,
    )
    _start_pitch(session)
    _player_for_client(session, request.headers.get("X-Room-Client-ID"))
    session.investor_portfolios = create_simulated_portfolios(SHARKS)
    await refresh_simulated_portfolios(session.investor_portfolios, session.pitch_index + 1)
    SESSIONS.put(session)
    return _public_state(session, request.headers.get("X-Room-Client-ID"))


def _get_session(session_id: str) -> GameSession:
    active = ACTIVE_SESSION.get()
    session = active if active and active.session_id == session_id else SESSIONS.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found; start a new game.")
    return session


async def _ensure_investor_portfolios(session: GameSession) -> bool:
    """Backfill portfolios for sessions created before the portfolio feature existed."""
    if session.investor_portfolios:
        return False
    session.investor_portfolios = create_simulated_portfolios(SHARKS)
    await refresh_simulated_portfolios(session.investor_portfolios, session.pitch_index + 1)
    return True


def _serialize_session(handler):
    @wraps(handler)
    async def wrapped(session_id: str, *args, **kwargs):
        async with SESSIONS.lock_for(session_id):
            session = _get_session(session_id)
            request = kwargs.get("request")
            client_id = request.headers.get("X-Room-Client-ID") if isinstance(request, Request) else None
            _player_for_client(session, client_id)
            await _ensure_investor_portfolios(session)
            context_token = ACTIVE_SESSION.set(session)
            try:
                result = await handler(session_id, *args, **kwargs)
                SESSIONS.put(session)
                await ROOM_HUB.broadcast_state(
                    session_id,
                    _public_state(session),
                    exclude_client_id=client_id,
                    state_for_client=lambda recipient_id: _public_state(session, recipient_id),
                )
                return result
            finally:
                ACTIVE_SESSION.reset(context_token)
    return wrapped


@app.get("/api/sessions/{session_id}")
async def get_session(session_id: str, request: Request) -> dict:
    async with SESSIONS.lock_for(session_id):
        session = _get_session(session_id)
        client_id = request.headers.get("X-Room-Client-ID")
        _, player_added = _player_for_client(session, client_id)
        portfolios_changed = await _ensure_investor_portfolios(session)
        if player_added and session.pitch_index + 1 >= session.total_pitches and session.phase in ("pitch_review", "pitch_result"):
            _scorecards_for_session(session)
        if player_added or portfolios_changed:
            SESSIONS.put(session)
            if player_added:
                await ROOM_HUB.broadcast_state(
                    session_id,
                    _public_state(session),
                    exclude_client_id=client_id,
                    state_for_client=lambda recipient_id: _public_state(session, recipient_id),
                )
        return _public_state(session, client_id)


@app.websocket("/api/sessions/{session_id}/live")
async def live_session(websocket: WebSocket, session_id: str) -> None:
    origin = websocket.headers.get("origin", "").rstrip("/")
    client_id = websocket.query_params.get("client_id", "")
    if (origin and origin not in _cors_origins()) or not client_id or len(client_id) > 100:
        await websocket.close(code=1008)
        return
    client = await ROOM_HUB.connect(session_id, websocket, client_id)
    try:
        async with SESSIONS.lock_for(session_id):
            session = _get_session(session_id)
            if not any(player.get("client_id") == client_id for player in session.players):
                raise HTTPException(status_code=403, detail="Join the game through its invite before opening the live connection.")
            await ROOM_HUB.send_state(websocket, _public_state(session, client_id))
        while True:
            # Receiving small client heartbeats keeps idle proxies from closing the room.
            await websocket.receive_text()
    except HTTPException:
        await websocket.close(code=1008)
    except WebSocketDisconnect:
        pass
    finally:
        await ROOM_HUB.disconnect(session_id, client)


@app.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str, request: Request) -> dict:
    async with SESSIONS.lock_for(session_id):
        session = _get_session(session_id)
        player, _ = _player_for_client(session, request.headers.get("X-Room-Client-ID"))
        if not player.get("is_host"):
            raise HTTPException(status_code=403, detail="Only the host player can reset this shared game.")
        await ROOM_HUB.broadcast_event(
            session_id,
            {"type": "room_closed", "message": "The host ended this game session."},
            exclude_client_id=request.headers.get("X-Room-Client-ID"),
        )
        SESSIONS.delete(session_id)
    return {"ok": True}


def _append_question_exchange(
    session: GameSession,
    question: str,
    topic: str | None,
    exchange: dict,
    player: dict | None = None,
) -> None:
    if topic and topic not in session.disclosures:
        session.disclosures.append(topic)
    question_message = _new_message(player["name"] if player else "You", question, "question", session.round_number)
    if player:
        question_message["player_id"] = player["id"]
    session.messages.append(question_message)
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
async def ask_question(session_id: str, payload: AskQuestion, request: Request) -> dict:
    session = _get_session(session_id)
    player = _require_player_turn(session, request.headers.get("X-Room-Client-ID"))
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
            session.investor_portfolios,
        )
    except DialogueProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    _append_question_exchange(session, question, topic, exchange, player)
    return _public_state(session, request.headers.get("X-Room-Client-ID"))


@app.post("/api/sessions/{session_id}/question/stream")
async def ask_question_stream(session_id: str, payload: AskQuestion, request: Request):
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
            player, added = _player_for_client(active, request.headers.get("X-Room-Client-ID"))
            if added:
                SESSIONS.put(active)
            if await _ensure_investor_portfolios(active):
                SESSIONS.put(active)
            if active.phase != "investigate" or active.question_asked:
                yield _sse("error", {"detail": "This round has already changed. Refresh the game and try again."})
                return
            if player.get("out") or active.current_player_id != player["id"]:
                current_player = _player_by_id(active, active.current_player_id)
                owner = current_player["name"] if current_player else "another investor"
                yield _sse("error", {"detail": f"It is {owner}'s turn. Wait for your turn before asking a question."})
                return

            yield _sse("message_start", {
                "field": "player_question",
                "speaker": player["name"],
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
                    active.investor_portfolios,
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
                _append_question_exchange(active, question, topic, exchange, player)
                SESSIONS.put(active)
                await ROOM_HUB.broadcast_state(
                    session_id,
                    _public_state(active),
                    exclude_client_id=request.headers.get("X-Room-Client-ID"),
                    state_for_client=lambda recipient_id: _public_state(active, recipient_id),
                )
                yield _sse("complete", _public_state(active, request.headers.get("X-Room-Client-ID")))
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
async def submit_decision(session_id: str, payload: SubmitDecision, request: Request) -> dict:
    session = _get_session(session_id)
    if session.phase != "investigate":
        raise HTTPException(status_code=409, detail="This pitch is already resolved.")
    client_id = request.headers.get("X-Room-Client-ID")
    player = _require_player_turn(session, client_id)
    assessment = assess(session.pitch["profile"], session.pitch["ask_amount"])
    benchmark_data = benchmark(assessment, session.pitch["profile"], session.pitch["ask_amount"])

    if payload.action == "offer":
        if player.get("out"):
            raise HTTPException(status_code=409, detail="You are out on this pitch and cannot make another offer.")
        if payload.amount is None or payload.rate is None:
            raise HTTPException(status_code=422, detail="A loan offer needs an amount and annual interest rate.")
        offer = {
            "id": str(uuid.uuid4()),
            "investor_id": player["id"],
            "player_id": player["id"],
            "investor": player["name"],
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
        if payload.amount > player["balance"]:
            raise HTTPException(status_code=422, detail=f"Your remaining capital is ${player['balance']:,}.")
        offer_message = _new_message(player["name"], _player_offer_text(offer), "offer", session.round_number)
        offer_message["player_id"] = player["id"]
        if offer_matches_request(session.pitch, offer):
            for previous in session.offers:
                if previous.get("player_id", previous["investor_id"]) == player["id"] and previous["status"] == "pending":
                    previous["status"] = "withdrawn"
            session.offers.append(offer)
            session.messages.append(offer_message)
            investor_name = "Guest shrimp" if player["id"] == "human_user" else player["name"]
            acceptance = _new_message(
                session.pitch["founder"],
                f"{investor_name}, those terms meet my request. I accept your offer. We have a deal.",
                "answer", session.round_number,
            )
            acceptance["source"] = "system"
            session.messages.append(acceptance)
            session.last_new_offer_round = session.round_number
            _finish_pitch(session, assessment, benchmark_data, offer, reason="matched_request")
            return _public_state(session, client_id)
        offer_context = [*session.messages, offer_message]
        try:
            exchange = await table_exchange(
                session.pitch, offer_context, session.round_number, player_offer=offer,
                investor_portfolios=session.investor_portfolios,
            )
            # A player can revise only their own pending bid; other human bids remain live.
            carried_offers = [
                item for item in session.offers
                if not (item.get("player_id", item["investor_id"]) == player["id"] and item["status"] == "pending")
            ]
            shark_offer, counters = await _round_follow_up(
                session,
                assessment,
                [*carried_offers, offer],
                session.round_number,
                _messages_with_exchange(offer_context, exchange, session.pitch["founder"]),
                responded_offer_id=offer["id"] if exchange.get("founder_offer_reply") else None,
            )
        except DialogueProviderError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        # Generate before changing bids so a provider failure leaves the turn retryable.
        before_ids = {item["id"] for item in session.offers}
        for previous in session.offers:
            if previous.get("player_id", previous["investor_id"]) == player["id"] and previous["status"] == "pending":
                previous["status"] = "withdrawn"
        session.offers.append(offer)
        session.messages.append(offer_message)
        _append_ai_table_exchange(session, exchange)
        _settle_round(session, assessment, benchmark_data, before_ids, shark_offer, counters)
        return _public_state(session, client_id)
    elif payload.action == "out":
        out_message = _new_message(
            "Stage manager",
            f"{player['name']} is out. The other investors continue at the table.",
            "round",
            session.round_number,
        )
        out_message["player_id"] = player["id"]
        other_active = any(not participant.get("out") for participant in session.players if participant["id"] != player["id"])
        if not other_active:
            player["out"] = True
            if player["id"] == "human_user":
                session.human_out = True
            session.messages.append(out_message)
            try:
                await _complete_ai_negotiation(session, assessment, benchmark_data)
            except DialogueProviderError as exc:
                player["out"] = False
                if player["id"] == "human_user":
                    session.human_out = False
                session.messages.remove(out_message)
                raise HTTPException(status_code=502, detail=str(exc)) from exc
            return _public_state(session, client_id)
        try:
            projected_offers = [dict(offer) for offer in session.offers]
            for offer in projected_offers:
                if offer.get("player_id", offer.get("investor_id")) == player["id"] and offer["status"] == "pending":
                    offer["status"] = "withdrawn"
            projected_messages = [*session.messages, out_message]
            exchange = await table_exchange(
                session.pitch, projected_messages, session.round_number,
                investor_portfolios=session.investor_portfolios,
            )
            shark_offer, counters = await _round_follow_up(
                session,
                assessment,
                projected_offers,
                session.round_number,
                _messages_with_exchange(projected_messages, exchange, session.pitch["founder"]),
            )
        except DialogueProviderError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        player["out"] = True
        if player["id"] == "human_user":
            session.human_out = True
        for previous in session.offers:
            if previous.get("player_id", previous.get("investor_id")) == player["id"] and previous["status"] == "pending":
                previous["status"] = "withdrawn"
        session.messages.append(out_message)
        before_ids = {item["id"] for item in session.offers}
        _append_ai_table_exchange(session, exchange)
        _settle_round(session, assessment, benchmark_data, before_ids, shark_offer, counters)
        return _public_state(session, client_id)
    elif payload.action == "pass":
        pass_message = _new_message(player["name"], "I pass on this round.", "pass", session.round_number)
        pass_message["player_id"] = player["id"]
        try:
            projected_messages = [*session.messages, pass_message]
            exchange = await table_exchange(
                session.pitch, projected_messages, session.round_number,
                investor_portfolios=session.investor_portfolios,
            )
            shark_offer, counters = await _round_follow_up(
                session,
                assessment,
                session.offers,
                session.round_number,
                _messages_with_exchange(projected_messages, exchange, session.pitch["founder"]),
            )
        except DialogueProviderError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        before_ids = {item["id"] for item in session.offers}
        session.messages.append(pass_message)
        _append_ai_table_exchange(session, exchange)
        _settle_round(session, assessment, benchmark_data, before_ids, shark_offer, counters)
    return _public_state(session, client_id)


@app.post("/api/sessions/{session_id}/next")
@_serialize_session
async def next_pitch(session_id: str, request: Request) -> dict:
    session = _get_session(session_id)
    if session.phase != "pitch_result":
        raise HTTPException(status_code=409, detail="There is no completed pitch waiting to advance.")
    session.pitch_index += 1
    _start_pitch(session)
    await refresh_simulated_portfolios(session.investor_portfolios, session.pitch_index + 1)
    return _public_state(session, request.headers.get("X-Room-Client-ID"))


@app.post("/api/sessions/{session_id}/reveal")
@_serialize_session
async def reveal_decision(session_id: str, request: Request) -> dict:
    session = _get_session(session_id)
    if session.phase != "pitch_review" or not session.pending_result:
        raise HTTPException(status_code=409, detail="There is no founder decision ready to reveal.")
    session.result = session.pending_result
    session.pending_result = None
    session.phase = "pitch_result"
    return _public_state(session, request.headers.get("X-Room-Client-ID"))


@app.get("/api/sessions/{session_id}/scorecard")
async def get_scorecard(session_id: str) -> dict:
    session = _get_session(session_id)
    if session.phase != "complete" or not session.scorecard:
        raise HTTPException(status_code=409, detail="The scorecard is available after the final pitch.")
    return session.scorecard
