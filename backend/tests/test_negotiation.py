"""Round progression, quiet-offer closes, and named founder counters. Offline only."""

import os
import unittest
from unittest.mock import patch

os.environ["SESSION_STORE"] = "memory"

from fastapi.testclient import TestClient

from backend.app import agents
from backend.app.catalog import PROFILES
from backend.app.main import SESSIONS, _shark_counter_replies, app
from backend.app.underwriting import assess


def _sample(pitch_id):
    def sample(self, population, k):
        chosen = [item for item in population if item["id"] == pitch_id]
        if len(chosen) != 1:
            raise AssertionError(f"catalog is missing {pitch_id}")
        return chosen[:k]
    return sample


class NegotiationTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {"GROK_API_KEY": ""})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.market = patch("backend.app.portfolio_agent.get_coinbase_market_snapshot", return_value={})
        self.market.start()
        self.addCleanup(self.market.stop)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def start(self, pitch_id):
        with patch("backend.app.main.random.SystemRandom.sample", _sample(pitch_id)):
            response = self.client.post("/api/sessions", json={"total_pitches": 1, "difficulty": "medium"})
        self.assertEqual(response.status_code, 200, response.text)
        state = response.json()
        self.assertEqual(state["round"], 1)
        self.assertEqual(state["quiet_rounds"], 0)
        self.assertEqual(state["quiet_round_limit"], 3)
        self.assertNotIn("max_rounds", state)
        return state

    def decide(self, session_id, **payload):
        response = self.client.post(f"/api/sessions/{session_id}/decision", json=payload)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def pass_until_closed(self, session_id, limit=12):
        state = None
        for _ in range(limit):
            state = self.decide(session_id, action="pass")
            if state["phase"] != "investigate":
                return state
        self.fail(f"pitch stayed open through round {state['round']}")

    def test_rounds_continue_past_one_until_offers_go_quiet(self):
        state = self.start("p10")
        offered = self.decide(
            state["id"], action="offer", amount=135_000, rate=9, royalty=0, term_months=36, secured=False,
        )
        self.assertEqual(offered["phase"], "investigate")
        self.assertEqual(offered["round"], 2)

        closed = self.pass_until_closed(offered["id"])
        self.assertEqual(closed["phase"], "pitch_review")
        self.assertGreater(closed["round"], 3)
        counters = [message for message in closed["messages"] if message["kind"] == "counter"]
        self.assertGreaterEqual(len(counters), 3)
        named = " ".join(message["text"] for message in counters)
        for shark in ("Kevin O'Leary", "Lori Greiner", "Mark Cuban"):
            self.assertIn(shark, named)
        for message in counters:
            self.assertTrue(
                "Guest shrimp" in message["text"]
                or any(shark in message["text"] for shark in ("Kevin O'Leary", "Lori Greiner", "Mark Cuban")),
                message["text"],
            )

        revealed = self.client.post(f"/api/sessions/{closed['id']}/reveal", json={})
        self.assertEqual(revealed.status_code, 200, revealed.text)
        self.assertEqual(revealed.json()["result"]["outcome"], "deal")

    def test_a_matching_offer_closes_immediately_without_calling_grok(self):
        state = self.start("p10")
        pitch = next(item for item in PROFILES if item["id"] == "p10")
        with patch.dict(os.environ, {"GROK_API_KEY": "test"}), \
                patch("backend.app.main.table_exchange", side_effect=AssertionError("Unexpected Grok table request")), \
                patch("backend.app.main.founder_counters", side_effect=AssertionError("Unexpected Grok counter request")):
            offered = self.decide(state["id"], action="offer", amount=pitch["ask_amount"],
                                  rate=pitch["opening_rate"], royalty=0, term_months=36, secured=False)
        added = offered["messages"][len(state["messages"]):]
        self.assertEqual(added[0]["speaker"], "You")
        self.assertEqual(added[1]["speaker"], pitch["founder"])
        self.assertIn("meet my request", added[1]["text"])
        self.assertIn("I accept your offer", added[1]["text"])
        self.assertEqual(added[1]["source"], "system")
        self.assertFalse(any(message["kind"] == "shark_question" for message in added))
        replies_to_player = [message for message in added if message["speaker"] == pitch["founder"]
                             and "Guest shrimp" in message["text"]]
        self.assertEqual(len(replies_to_player), 1)
        self.assertEqual(offered["phase"], "pitch_review")
        self.assertTrue(offered["immediate_acceptance"])
        self.assertEqual(offered["round"], 1)
        self.assertEqual(offered["balance"], state["balance"] - pitch["ask_amount"])
        self.assertEqual(offered["offers"][0]["status"], "accepted")
        self.assertIsNone(offered["result"])

    def test_matching_a_risky_founders_request_still_accepts_and_scores_the_risk(self):
        for pitch_id in ("spindle-loom", "brightline-pantry"):
            with self.subTest(pitch=pitch_id):
                state = self.start(pitch_id)
                pitch = next(item for item in PROFILES if item["id"] == pitch_id)
                offered = self.decide(state["id"], action="offer", amount=pitch["ask_amount"],
                                      rate=pitch["opening_rate"], royalty=0, term_months=36, secured=False)
                self.assertTrue(offered["immediate_acceptance"])
                revealed = self.client.post(f"/api/sessions/{state['id']}/reveal", json={}).json()
                self.assertEqual(revealed["result"]["outcome"], "deal")
                self.assertEqual(revealed["result"]["reason"], "matched_request")
                self.assertLess(revealed["scorecard"]["pitches"][0]["decision_score"], 100)
                feedback = revealed["scorecard"]["pitches"][0]["feedback"]
                self.assertTrue("walk away" in feedback or "did not fully compensate" in feedback)

    def test_partial_funding_higher_rate_or_royalty_do_not_trigger_instant_acceptance(self):
        for amount, rate, royalty in ((130_000, 7, 0), (135_000, 7.5, 0), (135_000, 7, 0.25)):
            with self.subTest(amount=amount, rate=rate, royalty=royalty):
                state = self.start("p10")
                offered = self.decide(state["id"], action="offer", amount=amount, rate=rate,
                                      royalty=royalty, term_months=36, secured=False)
                self.assertFalse(offered["immediate_acceptance"])
                self.assertEqual(offered["phase"], "investigate")
                self.assertEqual(offered["balance"], state["balance"])

    def test_better_terms_accept_and_repeated_submission_does_not_debit_twice(self):
        state = self.start("p10")
        payload = dict(action="offer", amount=140_000, rate=6.5, royalty=0, term_months=48, secured=True)
        offered = self.decide(state["id"], **payload)
        self.assertTrue(offered["immediate_acceptance"])
        repeated = self.client.post(f"/api/sessions/{state['id']}/decision", json=payload)
        self.assertEqual(repeated.status_code, 409)
        saved = SESSIONS.get(state["id"])
        self.assertEqual(len(saved.completed), 1)
        self.assertEqual(saved.players[0]["balance"], state["balance"] - 140_000)

    def test_matching_offer_still_requires_available_capital_and_valid_amount(self):
        state = self.start("p19")
        for amount in (260_000, 350_000):
            with self.subTest(amount=amount):
                response = self.client.post(f"/api/sessions/{state['id']}/decision", json={
                    "action": "offer", "amount": amount, "rate": 7, "royalty": 0,
                })
                self.assertEqual(response.status_code, 422)
                saved = self.client.get(f"/api/sessions/{state['id']}").json()
                self.assertEqual(saved["balance"], state["balance"])
                self.assertEqual(saved["offers"], [])
                self.assertEqual(saved["phase"], "investigate")

    def test_guest_matching_offer_wins_over_pending_host_bid_and_charges_only_guest(self):
        state = self.start("p10")
        host_headers = {"X-Room-Client-ID": "host-browser"}
        guest_headers = {"X-Room-Client-ID": "guest-browser"}
        host = self.client.get(f"/api/sessions/{state['id']}", headers=host_headers).json()
        guest = self.client.get(f"/api/sessions/{state['id']}", headers=guest_headers).json()
        host_bid = self.client.post(f"/api/sessions/{state['id']}/decision", headers=host_headers,
                                   json={"action": "offer", "amount": 135_000, "rate": 9, "royalty": 0})
        self.assertEqual(host_bid.status_code, 200, host_bid.text)
        guest_bid = self.client.post(f"/api/sessions/{state['id']}/decision", headers=guest_headers,
                                    json={"action": "offer", "amount": 135_000, "rate": 7, "royalty": 0})
        self.assertEqual(guest_bid.status_code, 200, guest_bid.text)
        accepted = guest_bid.json()
        self.assertTrue(accepted["immediate_acceptance"])
        self.assertEqual(accepted["balance"], guest["balance"] - 135_000)
        self.assertEqual(accepted["offers"][0]["investor_id"], guest["self_player_id"])
        saved_host = self.client.get(f"/api/sessions/{state['id']}", headers=host_headers).json()
        self.assertTrue(saved_host["immediate_acceptance"])
        self.assertEqual(saved_host["balance"], host["balance"])
        self.assertEqual(saved_host["messages"], accepted["messages"])
        self.assertTrue(any(offer["status"] == "rejected" for offer in SESSIONS.get(state["id"]).offers))
        revealed = self.client.post(f"/api/sessions/{state['id']}/reveal", headers=guest_headers, json={}).json()
        self.assertEqual(revealed["result"]["winner"], guest["self_player_id"])
        self.assertEqual(revealed["scorecard"]["deals_funded"], 1)

    def test_immediate_acceptance_keeps_transcript_and_advances_to_next_pitch(self):
        pitches = [next(p for p in PROFILES if p["id"] == key) for key in ("p10", "p13")]
        with patch("backend.app.main.random.SystemRandom.sample", return_value=pitches):
            state = self.client.post("/api/sessions", json={"total_pitches": 2}).json()
        offered = self.decide(state["id"], action="offer", amount=135_000, rate=7, royalty=0)
        revealed = self.client.post(f"/api/sessions/{state['id']}/reveal", json={}).json()
        self.assertEqual(revealed["messages"], offered["messages"])
        next_pitch = self.client.post(f"/api/sessions/{state['id']}/next", json={})
        self.assertEqual(next_pitch.status_code, 200, next_pitch.text)
        advanced = next_pitch.json()
        self.assertEqual(advanced["phase"], "investigate")
        self.assertEqual(advanced["pitch_index"], 2)
        self.assertFalse(advanced["immediate_acceptance"])
        self.assertEqual(advanced["balance"], state["balance"] - 135_000)

    def test_three_rounds_with_no_offers_end_without_a_deal(self):
        state = self.start("spindle-loom")
        once = self.decide(state["id"], action="pass")
        self.assertEqual(once["phase"], "investigate")
        self.assertEqual(once["round"], 2)
        self.assertEqual(once["quiet_round_limit"], 3)
        closed = self.pass_until_closed(state["id"])
        self.assertEqual(closed["phase"], "pitch_review")
        self.assertEqual(closed["round"], 3)
        self.assertFalse(any(message["kind"] == "counter" for message in closed["messages"]))
        revealed = self.client.post(f"/api/sessions/{closed['id']}/reveal", json={})
        body = revealed.json()
        self.assertEqual(body["result"]["outcome"], "no_deal")
        self.assertEqual(body["scorecard"]["decision_accuracy"], 100)
        self.assertEqual(body["scorecard"]["overall_score"], 90)

    def test_a_live_offer_waits_for_one_quiet_round_before_it_is_accepted(self):
        state = self.start("northstar-cold-chain")
        offered = self.decide(
            state["id"], action="offer", amount=210_000, rate=9, royalty=0, term_months=36, secured=False,
        )
        self.assertEqual(offered["phase"], "investigate")
        self.assertEqual(offered["round"], 2)
        self.assertEqual(offered["quiet_rounds"], 0)
        self.assertEqual(offered["quiet_round_limit"], 1)
        spoken = [message for message in offered["messages"] if message["speaker"] == "You" and message["kind"] == "offer"]
        self.assertEqual(len(spoken), 1)
        self.assertIn("$210,000", spoken[0]["text"])
        self.assertIn("9.00%", spoken[0]["text"])
        offer_index = offered["messages"].index(spoken[0])
        self.assertEqual(
            [(message["speaker"], message["kind"]) for message in offered["messages"][offer_index + 1:offer_index + 5]],
            [(offered["pitch"]["founder"], "counter"), ("Kevin O'Leary", "shark_question"),
             (offered["pitch"]["founder"], "answer"), ("Lori Greiner", "shark_question")],
        )
        self.assertTrue(any(
            message["kind"] == "counter" and "Guest shrimp" in message["text"]
            for message in offered["messages"]
        ))

        closed = self.pass_until_closed(offered["id"])
        self.assertEqual(closed["phase"], "pitch_review")
        self.assertGreater(closed["round"], 3)
        revealed = self.client.post(f"/api/sessions/{closed['id']}/reveal", json={})
        body = revealed.json()
        self.assertEqual(body["result"]["winner"], "human_user")
        self.assertEqual(body["scorecard"]["decision_accuracy"], 100)
        self.assertEqual(body["scorecard"]["expected_profit"], 48_300)
        self.assertEqual(body["scorecard"]["overall_score"], 94)

    def test_an_offer_that_misses_the_founders_terms_can_be_rejected(self):
        state = self.start("spindle-loom")
        offered = self.decide(
            state["id"], action="offer", amount=160_000, rate=9.5, royalty=0, term_months=36, secured=False,
        )
        self.assertTrue(any(message["speaker"] == "You" and message["kind"] == "offer" for message in offered["messages"]))
        self.assertTrue(any("Guest shrimp" in message["text"] for message in offered["messages"] if message["kind"] == "counter"))
        closed = self.pass_until_closed(offered["id"])
        self.assertEqual(closed["phase"], "pitch_review")
        revealed = self.client.post(f"/api/sessions/{closed['id']}/reveal", json={})
        body = revealed.json()
        self.assertEqual(body["result"]["outcome"], "no_deal")
        self.assertIsNone(body["result"]["winner"])
        self.assertEqual(body["scorecard"]["decision_accuracy"], 100)
        self.assertEqual(body["scorecard"]["overall_score"], 90)

    def test_a_new_offer_resets_the_quiet_clock(self):
        state = self.start("spindle-loom")
        offered = self.decide(
            state["id"], action="offer", amount=160_000, rate=9.5, royalty=0, term_months=36, secured=False,
        )
        self.assertEqual(offered["quiet_rounds"], 0)
        self.assertEqual(offered["phase"], "investigate")
        refreshed = self.decide(
            offered["id"], action="offer", amount=160_000, rate=9.75, royalty=0, term_months=36, secured=False,
        )
        self.assertEqual(refreshed["phase"], "investigate")
        self.assertEqual(refreshed["quiet_rounds"], 0)
        stalled = self.start("spindle-loom")
        stalled = self.decide(
            stalled["id"], action="offer", amount=160_000, rate=9.5, royalty=0, term_months=36, secured=False,
        )
        self.assertEqual(stalled["quiet_round_limit"], 1)
        closed = self.decide(stalled["id"], action="pass")
        self.assertEqual(closed["phase"], "pitch_review")
        self.assertEqual(closed["round"], 2)
        self.assertEqual(closed["quiet_rounds"], 1)

    def test_leaving_after_a_question_still_reaches_a_named_counter(self):
        state = self.start("p10")
        asked = self.client.post(
            f"/api/sessions/{state['id']}/question",
            json={"question": "How much free cash flow do you have after payroll?"},
        )
        self.assertEqual(asked.status_code, 200, asked.text)
        self.assertTrue(asked.json()["question_asked"])
        closed = self.decide(state["id"], action="out")
        self.assertEqual(closed["phase"], "pitch_review")
        self.assertGreater(closed["round"], 3)
        named = " ".join(message["text"] for message in closed["messages"] if message["kind"] == "counter")
        self.assertIn("Kevin O'Leary", named)

    def test_leaving_still_counters_each_shark_before_the_founder_chooses(self):
        state = self.start("p10")
        closed = self.decide(state["id"], action="out")
        self.assertEqual(closed["phase"], "pitch_review")
        self.assertGreater(closed["round"], 3)
        named = " ".join(message["text"] for message in closed["messages"] if message["kind"] == "counter")
        for shark in ("Kevin O'Leary", "Lori Greiner", "Mark Cuban"):
            self.assertIn(shark, named)
        speakers = {message["speaker"] for message in closed["messages"] if message["kind"] == "reply"}
        self.assertEqual(speakers, {"Kevin O'Leary", "Lori Greiner", "Mark Cuban"})

    def test_exit_recovers_from_an_invalid_investor_question(self):
        state = self.start("p10")
        attempts = []

        async def fake_grok_stream(instructions, context, schema_name, properties, max_tokens=420):
            self.assertEqual(schema_name, "shrimp_tank_table_exchange")
            attempts.append(instructions)
            yield {"type": "result", "value": {
                "shark_question": "Why?" if len(attempts) == 1 else "What supports dependable repayment from those customers?",
                "founder_answer": context["founder_verified_fact"],
                "shark_reaction": "That helps, but execution still matters here.",
            }}

        with patch.dict(os.environ, {"GROK_API_KEY": "test"}), \
                patch.object(agents, "_grok_json_stream", fake_grok_stream), \
                patch("backend.app.main.founder_counters", return_value=[]):
            response = self.client.post(f"/api/sessions/{state['id']}/decision", json={"action": "out"})
        self.assertEqual(response.status_code, 200, response.text)
        closed = response.json()
        self.assertEqual(closed["phase"], "pitch_review")
        self.assertGreaterEqual(len(attempts), 3)
        self.assertIn("previous response failed", attempts[1])
        self.assertFalse(any(message["text"] == "Why?" for message in closed["messages"]))
        self.assertTrue(any(message["source"] == "xai" for message in closed["messages"] if message["kind"] == "shark_question"))

    def test_exhausted_exit_retry_preserves_the_session(self):
        state = self.start("p10")
        attempts = []

        async def fake_grok_stream(instructions, context, schema_name, properties, max_tokens=420):
            attempts.append(instructions)
            yield {"type": "result", "value": {
                "shark_question": "Why?",
                "founder_answer": context["founder_verified_fact"],
                "shark_reaction": "That helps, but execution still matters here.",
            }}

        with patch.dict(os.environ, {"GROK_API_KEY": "test"}), \
                patch.object(agents, "_grok_json_stream", fake_grok_stream):
            response = self.client.post(f"/api/sessions/{state['id']}/decision", json={"action": "out"})
        self.assertEqual(response.status_code, 502)
        self.assertIn("investor question", response.json()["detail"])
        self.assertEqual(len(attempts), 3)
        saved = self.client.get(f"/api/sessions/{state['id']}")
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.json(), state)

    def test_sharks_answer_a_counter_and_only_some_revise_the_bid(self):
        state = self.start("p10")
        state = self.decide(
            state["id"], action="offer", amount=135_000, rate=9, royalty=0, term_months=36, secured=False,
        )
        for _ in range(3):
            state = self.decide(state["id"], action="pass")
        self.assertEqual(state["round"], 5)
        self.assertEqual(state["phase"], "investigate")
        pending = {offer["investor_id"]: offer for offer in state["offers"]}
        self.assertEqual(set(pending), {"human_user", "kevin", "lori", "mark"})
        self.assertEqual(pending["kevin"]["rate"], 10.25)
        self.assertEqual(pending["kevin"]["royalty"], 0)
        self.assertEqual(pending["lori"]["rate"], 10.5)
        self.assertEqual(pending["lori"]["royalty"], 0)
        self.assertEqual(pending["mark"]["rate"], 9.5)
        self.assertEqual(pending["mark"]["royalty"], 0.25)
        replies = [message for message in state["messages"] if message["kind"] == "reply"]
        self.assertTrue(any(
            message["speaker"] == "Kevin O'Leary" and message["text"] == "That counter doesn't change my terms."
            for message in replies
        ))
        self.assertTrue(any(
            message["speaker"] == "Lori Greiner"
            and message["text"] == "I can come down a little. My rate is now 10.50%."
            for message in replies
        ))
        self.assertTrue(any(
            message["speaker"] == "Mark Cuban"
            and message["text"] == "I'll trim the rate to 9.50% and the royalty to 0.25%."
            for message in replies
        ))
        self.assertTrue(all(message["source"] == "offline" for message in replies))

        # The next round has no new offer, so the one-round clock closes the pitch.
        # Lori's revision was on round 4 and must stay put.
        held = self.decide(state["id"], action="pass")
        self.assertEqual(held["phase"], "pitch_review")
        self.assertEqual(held["round"], 5)
        self.assertEqual(held["quiet_rounds"], 1)
        self.assertTrue(any(
            message["speaker"] == "Mark Cuban" and message["text"] == "I'm staying with the offer I put down."
            for message in held["messages"]
            if message["kind"] == "reply"
        ))
        self.assertTrue(any(
            message["speaker"] == "Lori Greiner" and message["text"] == "I can come down a little. My rate is now 10.50%."
            for message in held["messages"]
        ))


class CounterVoiceTests(unittest.IsolatedAsyncioTestCase):
    def pitch(self):
        return next(item for item in PROFILES if item["id"] == "p10")

    def offer(self):
        return {
            "investor_id": "kevin",
            "investor": "Kevin O'Leary",
            "kind": "shark",
            "status": "pending",
            "amount": 135_000,
            "rate": 10.25,
            "royalty": 0,
            "term_months": 36,
            "secured": False,
        }

    async def test_a_counter_that_skips_the_name_or_invents_a_number_falls_back(self):
        async def unnamed(*_args, **_kwargs):
            return {"counter_kevin": "I need a better rate than that."}

        async def invented(*_args, **_kwargs):
            return {"counter_kevin": "Kevin O'Leary, your $135,000 at 10.25% is the offer I am looking at."}

        pitch = self.pitch()
        offer = self.offer()
        with patch.dict(os.environ, {"GROK_API_KEY": "test"}):
            with patch("backend.app.agents._grok_json", unnamed):
                missed = await agents.founder_counters(pitch, [offer], [])
            with patch("backend.app.agents._grok_json", invented):
                numbered = await agents.founder_counters(pitch, [offer], [])
        for counters in (missed, numbered):
            self.assertEqual(counters[0]["source"], "offline")
            self.assertIn("Kevin O'Leary", counters[0]["text"])
            self.assertNotIn("10.25", counters[0]["text"])

    async def test_a_named_counter_with_allowed_numbers_is_kept(self):
        async def named(*_args, **_kwargs):
            return {"counter_kevin": "Kevin O'Leary, I counter at $135,000 and 7.0%."}

        with patch.dict(os.environ, {"GROK_API_KEY": "test"}), patch("backend.app.agents._grok_json", named):
            counters = await agents.founder_counters(self.pitch(), [self.offer()], [])
        self.assertEqual(counters[0]["source"], "xai")
        self.assertIn("Kevin O'Leary", counters[0]["text"])

    def test_numbered_player_names_do_not_trigger_financial_number_fallback(self):
        pitch = self.pitch()
        offer = {**self.offer(), "investor_id": "seat-uuid", "investor": "Player 12", "kind": "human"}
        line = "Player 12, can we get closer to $135,000 at 7.0%?"
        kept = agents._counter_result(pitch, offer, line, "xai")
        self.assertEqual(kept["source"], "xai")
        self.assertEqual(kept["text"], line)
        invented = agents._counter_result(pitch, offer, "Player 12, I need $12 in additional fees.", "xai")
        self.assertEqual(invented["source"], "offline")
        wrong_name = agents._counter_result(pitch, {**offer, "investor": "Player 1"}, line, "xai")
        self.assertEqual(wrong_name["source"], "offline")

    async def test_the_player_is_countered_as_guest_shrimp(self):
        offer = {
            "investor_id": "human_user",
            "investor": "You",
            "kind": "human",
            "status": "pending",
            "amount": 160_000,
            "rate": 9.0,
            "royalty": 0,
            "term_months": 36,
            "secured": False,
        }

        async def named(*_args, **_kwargs):
            return {"counter_human_user": "Guest shrimp, I counter at $135,000 and 7.0%."}

        async def called_you(*_args, **_kwargs):
            return {"counter_human_user": "You, I am countering your 9.00%."}

        pitch = self.pitch()
        with patch.dict(os.environ, {"GROK_API_KEY": "test"}):
            with patch("backend.app.agents._grok_json", named):
                kept = await agents.founder_counters(pitch, [offer], [])
            with patch("backend.app.agents._grok_json", called_you):
                fallback = await agents.founder_counters(pitch, [offer], [])
        self.assertEqual(kept[0]["source"], "xai")
        self.assertIn("Guest shrimp", kept[0]["text"])
        self.assertEqual(fallback[0]["source"], "offline")
        self.assertIn("Guest shrimp", fallback[0]["text"])
        self.assertNotIn("You,", fallback[0]["text"])

    def _p10(self):
        pitch = self.pitch()
        return pitch, assess(pitch["profile"], pitch["ask_amount"])

    def _pending(self, investor_id, name, rate, royalty):
        return {
            "id": f"{investor_id}-bid",
            "investor_id": investor_id,
            "investor": name,
            "kind": "shark",
            "status": "pending",
            "amount": 135_000,
            "rate": rate,
            "royalty": royalty,
            "term_months": 36,
            "secured": False,
            "concessions": 0,
        }

    def test_lori_comes_down_once_and_then_holds(self):
        pitch, assessment = self._p10()
        offer = self._pending("lori", "Lori Greiner", 11.0, 0)
        counter = [{"investor_id": "lori"}]
        first = _shark_counter_replies([offer], counter, pitch, assessment, 4)
        self.assertEqual(first[0]["text"], "I can come down a little. My rate is now 10.50%.")
        revised = first[0]["replacement"]
        self.assertEqual(revised["rate"], 10.5)
        self.assertEqual(revised["royalty"], 0)
        self.assertEqual(revised["concessions"], 1)
        self.assertEqual(revised["amount"], offer["amount"])
        second = _shark_counter_replies(
            [{**offer, "status": "withdrawn"}, revised], counter, pitch, assessment, 5,
        )
        self.assertIsNone(second[0]["replacement"])
        self.assertEqual(second[0]["text"], "I want this to work, but I'm keeping the offer I made.")

    def test_mark_trims_rate_and_royalty_without_going_below_the_target(self):
        pitch, assessment = self._p10()
        offer = self._pending("mark", "Mark Cuban", 9.75, 0.5)
        counter = [{"investor_id": "mark"}]
        first = _shark_counter_replies([offer], counter, pitch, assessment, 3)
        self.assertEqual(first[0]["text"], "I'll trim the rate to 9.50% and the royalty to 0.25%.")
        self.assertEqual(first[0]["replacement"]["rate"], 9.5)
        self.assertEqual(first[0]["replacement"]["royalty"], 0.25)
        blocked = self._pending("mark", "Mark Cuban", 9.1, 0)
        held = _shark_counter_replies([blocked], counter, pitch, assessment, 3)
        self.assertIsNone(held[0]["replacement"])
        self.assertEqual(held[0]["text"], "I'm staying with the offer I put down.")

    def test_a_player_counter_does_not_get_a_shark_reply(self):
        pitch, assessment = self._p10()
        human = {
            "id": "human-bid",
            "investor_id": "human_user",
            "investor": "You",
            "kind": "human",
            "status": "pending",
            "amount": 135_000,
            "rate": 9.0,
            "royalty": 0,
            "term_months": 36,
            "secured": False,
        }
        replies = _shark_counter_replies([human], [{"investor_id": "human_user"}], pitch, assessment, 1)
        self.assertEqual(replies, [])

    def test_rounds_after_three_cycle_the_investors_and_topics(self):
        shark, nxt, topic, _question = agents._turn_sharks(4)
        self.assertEqual(shark["id"], "kevin")
        self.assertEqual(nxt["id"], "lori")
        self.assertEqual(topic, "conditions")
        self.assertEqual(agents._turn_sharks(3)[0]["id"], "mark")
