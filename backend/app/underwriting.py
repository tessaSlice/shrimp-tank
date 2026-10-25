from __future__ import annotations

from math import isfinite


GRADE_RATES = {1: 6.5, 2: 9.0, 3: 12.5, 4: 17.0, 5: None}
GRADE_LABELS = {
    1: "Prime",
    2: "Strong",
    3: "Moderate",
    4: "Substandard",
    5: "Impaired",
}


def _clamp(value: float, low: float = 0, high: float = 100) -> float:
    return max(low, min(high, value))


def assess(profile: dict, ask_amount: int) -> dict:
    """Deterministic teaching rubric; never a real credit or lending decision."""
    raw_score = profile.get("credit_score")
    if raw_score is None:
        # Missing or frozen files are unknown, not a zero score or evidence of
        # poor payment behavior. Keep character neutral and require review.
        character = 50.0
    else:
        score = float(raw_score)
        character = _clamp((score - 300) / 5.5 - profile["derogatory_count"] * 4)
        if profile.get("thin_file"):
            character = _clamp(character - 12)
        if profile.get("severe_delinquency"):
            character = _clamp(character - 20)

    monthly_payment = ask_amount * 0.034
    dscr = profile["monthly_free_cash_flow"] / max(1, monthly_payment + profile["monthly_existing_debt"])
    capacity = _clamp((dscr / 2.4) * 100)
    capital_ratio = profile["owner_equity"] / max(1, ask_amount)
    capital = _clamp(capital_ratio / 0.6 * 100)
    collateral_ratio = profile["collateral"] / max(1, ask_amount)
    collateral = _clamp(collateral_ratio / 0.9 * 100)
    conditions = _clamp(profile["market_strength"])

    components = {
        "character": round(character),
        "capacity": round(capacity),
        "capital": round(capital),
        "collateral": round(collateral),
        "conditions": round(conditions),
    }
    weights = {"character": 0.30, "capacity": 0.25, "capital": 0.15, "collateral": 0.15, "conditions": 0.15}
    total = round(sum(components[key] * weight for key, weight in weights.items()))
    grade = 1 if total >= 84 else 2 if total >= 68 else 3 if total >= 52 else 4 if total >= 36 else 5
    explanations = {
        "character": (
            "No credit score is available; verify identity and review alternative repayment evidence."
            if raw_score is None else
            "Personal credit history and disclosed derogatory signals."
        ),
        "capacity": f"Estimated debt-service coverage is {dscr:.2f}× at the requested amount.",
        "capital": f"Owner equity is {capital_ratio:.0%} of the requested loan.",
        "collateral": f"Estimated collateral covers {collateral_ratio:.0%} of the request.",
        "conditions": "Customer concentration, contract durability, and market resilience in this scenario.",
    }
    return {
        "grade": grade,
        "label": GRADE_LABELS[grade],
        "score": total,
        "components": components,
        "weights": weights,
        "explanations": explanations,
        "dscr": round(dscr, 2),
        "target_rate": GRADE_RATES[grade],
    }


def benchmark(assessment: dict, profile: dict, ask_amount: int) -> dict:
    grade = assessment["grade"]
    if grade == 5:
        return {"action": "walk_away", "amount": 0, "rate": None, "reason": "The simulated risk is outside this benchmark's lending appetite."}

    dscr = assessment["dscr"]
    capacity_fraction = _clamp((dscr - 0.75) / 1.45, 0.35, 1.0)
    collateral_fraction = _clamp(profile["collateral"] / max(1, ask_amount) + 0.25, 0.4, 1.0)
    amount = int(min(ask_amount, ask_amount * capacity_fraction, ask_amount * collateral_fraction) // 1000 * 1000)
    return {
        "action": "offer",
        "amount": max(25_000, amount),
        "rate": GRADE_RATES[grade],
        "reason": "Rules-based teaching benchmark using the same five-factor rubric; it is not a Coinbase trading-agent result.",
    }


def offer_is_affordable(offer: dict, ask_amount: int) -> bool:
    amount = offer.get("amount", 0)
    rate = offer.get("rate", 0)
    royalty = offer.get("royalty", 0)
    return (
        isinstance(amount, (int, float))
        and isinstance(rate, (int, float))
        and isinstance(royalty, (int, float))
        and isfinite(amount) and isfinite(rate) and isfinite(royalty)
        and amount >= ask_amount * 0.78
        and amount <= ask_amount * 1.5
        and 0 <= rate <= 40
        and 0 <= royalty <= 12
    )


def offer_matches_request(pitch: dict, offer: dict) -> bool:
    """Founder acceptance preference, independent of the investor's risk benchmark."""
    return (
        offer["amount"] >= pitch["ask_amount"]
        and offer["rate"] <= pitch["opening_rate"]
        and offer.get("royalty", 0) == 0
    )


def score_session(pitches: list[dict], starting_capital: int, player_id: str = "human_user") -> dict:
    rows = []
    total_expected_profit = 0.0
    earned = 0
    for item in pitches:
        assessment = item["assessment"]
        grade = assessment["grade"]
        player_offers = item.get("player_offers") or {}
        player_offer = player_offers.get(player_id)
        if player_offer is None and player_id == "human_user":
            player_offer = item.get("player_offer")
        accepted_by_player = item.get("winner") == player_id
        if not player_offers and player_id == "human_user":
            accepted_by_player = item.get("winner") == "human_user"
        ideal = item["benchmark"]
        if accepted_by_player and player_offer:
            principal = player_offer["amount"]
            rate = player_offer["rate"]
            risk_loss = {1: 0.01, 2: 0.04, 3: 0.12, 4: 0.30, 5: 0.75}[grade]
            expected_profit = principal * (rate / 100) * (player_offer["term_months"] / 12) - principal * risk_loss
            total_expected_profit += expected_profit
            earned += 1
            pricing_gap = abs(rate - (ideal["rate"] or rate))
            decision_score = max(0, 100 - int(pricing_gap * 8) - (20 if grade == 5 else 0))
            feedback = "You priced the risk close to the benchmark." if pricing_gap <= 2 else "Compare your rate with the benchmark and the borrower's repayment capacity."
            if grade == 5:
                feedback = "The founder accepted your terms, but the benchmark would walk away from this risk."
            elif grade == 4 and rate < (assessment["target_rate"] or 0):
                decision_score = max(0, decision_score - 25)
                feedback = "The rate did not fully compensate for the simulated risk."
        else:
            expected_profit = 0
            if grade == 5:
                decision_score = 100
                feedback = "Good discipline: you avoided a deal outside the benchmark's appetite." if not item.get("winner") else "The benchmark would have walked away from this risk."
            elif not item.get("winner") and grade <= 2:
                decision_score = 65
                feedback = "A strong borrower left without funding; consider whether a lower, well-supported return would fit."
            elif not item.get("winner"):
                decision_score = 82
                feedback = "You preserved capital. Review the benchmark amount and terms to see whether a protected offer was possible."
            else:
                decision_score = 78
                feedback = "Another investor won. Compare their terms with the risk grade before deciding whether to compete next time."
        rows.append({
            "pitch_id": item["pitch_id"],
            "company": item["company"],
            "archetype": item["archetype"],
            "grade": grade,
            "risk_label": assessment["label"],
            "decision": item.get("decision", "no_deal"),
            "winner": item.get("winner"),
            "winner_name": item.get("winner_name"),
            "player_offer": player_offer,
            "benchmark": ideal,
            "assessment": assessment,
            "expected_profit": round(expected_profit),
            "decision_score": decision_score,
            "feedback": feedback,
            "credit_score": item["credit_score"],
            "derogatory_count": item["profile"]["derogatory_count"],
            "monthly_free_cash_flow": item["profile"]["monthly_free_cash_flow"],
            "owner_equity": item["profile"]["owner_equity"],
            "collateral": item["profile"]["collateral"],
        })
    average = round(sum(row["decision_score"] for row in rows) / max(1, len(rows)))
    profit_score = max(0, min(100, round(50 + total_expected_profit / max(1, starting_capital) * 100)))
    overall = round(average * 0.8 + profit_score * 0.2)
    return {
        "overall_score": overall,
        "decision_accuracy": average,
        "expected_profit": round(total_expected_profit),
        "deals_funded": earned,
        "starting_capital": starting_capital,
        "pitches": rows,
        "notice": "Expected returns are illustrative game math, not forecasts or lending advice.",
    }
