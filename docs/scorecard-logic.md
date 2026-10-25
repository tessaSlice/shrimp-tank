# Scorecard Logic

This document describes the scorecard implemented in the current code. It is a deterministic teaching simulation, not a real credit decision, a lender policy, or a forecast.

## Founder profiles: what is fictional and where it comes from

The playable founders are bundled catalog entries in [`backend/app/catalog.py`](../backend/app/catalog.py). The credit-report facts are based on 19 synthetic CRS CalHacks sandbox personas. The founder names, companies, revenue, loan requests, business stories, operating figures, collateral estimates, and market conditions are locally authored fictional scenario details. There are no real applicants or live credit-report pulls in gameplay.

The profile is not generated when a player starts a pitch. Most scenario data is written directly into the catalog. `_crs_presenter(case)` shapes the extended persona cases into the same pitch format as the original entries, combining their fixed profile values with locally written founder and business details. `get_pitch(pitch_id)` returns a deep copy. When a session starts, the backend randomly selects pitch IDs, then `_start_pitch` copies the selected catalog entry into `GameSession.pitch`.

Grok may phrase a founder's dialogue using supplied facts, but it does not create or change the founder profile, five Cs assessment, benchmark, or deal outcome. The CRS MCP server informed development of the bundled examples; the running game does not call that server or the CRS API.

### Where the profile and scorecard are stored

The full profile lives in `GameSession.pitch["profile"]` while the pitch is active. `_finish_pitch` copies it into the completed-pitch record in `GameSession.completed`. At the end of the last pitch, the backend calculates the scorecard and assigns it to `GameSession.scorecard`.

With the default SpacetimeDB session store, [`backend/app/spacetime_store.py`](../backend/app/spacetime_store.py) serializes the `GameSession` fields (except its in-process lock) into the `state_json` column of the private `game_session` table. That snapshot includes the active pitch, completed profiles, and scorecard. The separate `conversation_message` table stores dialogue rows and does not store the founder profile. If `SESSION_STORE=memory` is explicitly selected, session data instead lives only in backend process memory and is lost on restart. The table definitions are in [`spacetime/spacetimedb/src/index.ts`](../spacetime/spacetimedb/src/index.ts).

The scorecard's “Reveal the founder's fictional profile” section shows a summary, not every raw profile field: credit score (or “No score”), derogatory-signal count, monthly free cash flow, owner equity, collateral, and calculated DSCR. Its five Cs bars show the derived component scores.

## Five Cs assessment and benchmark

[`backend/app/underwriting.py`](../backend/app/underwriting.py) contains the deterministic `assess`, `benchmark`, and `score_session` functions. `assess` calculates five component scores from 0 to 100, then uses these weights:

| Component | Calculation |
| --- | --- |
| Character | If no score is available, use 50. Otherwise, start with `(credit score − 300) / 5.5 − 4 × derogatory count`, subtract 12 for a thin file and 20 for severe delinquency, then clamp to 0–100. |
| Capacity | Estimate monthly payment as 3.4% of the requested principal. Divide monthly free cash flow by that payment plus existing monthly debt to get DSCR. Score `DSCR / 2.4 × 100`, clamped to 0–100. |
| Capital | Score `(owner equity / requested amount) / 0.6 × 100`, clamped to 0–100. |
| Collateral | Score `(collateral / requested amount) / 0.9 × 100`, clamped to 0–100. |
| Conditions | Use the scenario's `market_strength`, clamped to 0–100. |

The total is the rounded weighted sum: Character 30%, Capacity 25%, and Capital, Collateral, and Conditions 15% each. Grade cutoffs are: 1 / Prime at 84+, 2 / Strong at 68+, 3 / Moderate at 52+, 4 / Substandard at 36+, and 5 / Impaired below 36. Target rates for grades 1–4 are 6.5%, 9%, 12.5%, and 17%; grade 5 has no target rate.

`benchmark` turns that assessment into a comparison offer. Grade 5 maps to “walk away.” For other grades, it calculates a capacity fraction as `clamp((DSCR − 0.75) / 1.45, 0.35, 1)` and a collateral fraction as `clamp(collateral / ask + 0.25, 0.4, 1)`. It takes the lowest of the ask, ask multiplied by either fraction, rounds down to $1,000, applies a $25,000 minimum, and uses the grade's target rate. This is the game's rules-based comparison point; it is not an offer made by a bank or by Grok.

## “Decision Fit” vs. “Underwriting Instinct”

These are separate measures, and neither is the five Cs total.

### Decision Fit

For each pitch, `score_session` assigns a heuristic decision score from 0 to 100. The rules differ by outcome:

- If the player wins the deal, begin at 100 and subtract 8 points for each percentage point the player's rate differs from the benchmark rate. The code also applies a 20-point grade 5 penalty, though the current deal-eligibility rule blocks grade 5 offers because they have no target rate. A grade 4 offer below its target rate loses another 25 points. Scores cannot fall below zero.
- If the pitch is grade 5, award 100 points for the benchmark walk-away case. Grade 5 offers cannot currently win under the deal-eligibility rule.
- If nobody wins and the pitch is grade 1 or 2, award 65 points; if it is grade 3 or 4, award 82.
- If another investor wins, award 78 points.

**Decision Fit** is the rounded average of those per-pitch scores. The name describes a teaching heuristic: this is not a statistical accuracy rate and it is not a comparison against real loan outcomes.

### Underwriting Instinct

The score in the circle is `overall_score`, labeled “Underwriting Instinct.” It combines Decision Fit with a game-profit score:

1. For each deal won by the player, calculate expected game P&L as `principal × (annual rate / 100) × (term in months / 12) − principal × assumed loss rate`.
2. The assumed loss rate is grade-based: 1%, 4%, 12%, 30%, or 75% for grades 1 through 5. Pitches not funded by the player contribute zero expected P&L. The formula does not include royalties or model amortized payments.
3. Convert total expected P&L to a 0–100 profit score: `clamp(round(50 + total expected P&L / starting capital × 100), 0, 100)`.
4. Calculate **Underwriting Instinct** as `round(Decision Fit × 0.80 + profit score × 0.20)`.

Starting capital is $350,000 for Easy, $250,000 for Medium, and $175,000 for Hard. The displayed projected ending capital is starting capital plus total expected game P&L. These values are illustrative mechanics, not return estimates.

## When the scorecard is calculated and shown

The final scorecard is calculated in `_finish_pitch` when the last pitch closes. It is kept off the public session response during `pitch_review`, while the founder's decision is still hidden. After the player reveals that decision, the final pitch result contains the scorecard; the browser displays it when the player selects the continue action from that last result. The rendering and labels are in [`frontend/src/main.ts`](../frontend/src/main.ts).

There is one route inconsistency in the current implementation: `GET /api/sessions/{session_id}/scorecard` requires phase `complete`, but the backend's final-pitch flow does not set that phase, and the browser does not call this endpoint. The working UI path reads `scorecard` from the regular session response instead. This is an endpoint/phase mismatch, not part of the score calculation.

## Scope and caveats

- This rubric is hand-authored and not calibrated against repayment results or lender policy.
- “Decision Fit” and “Underwriting Instinct” are game labels for heuristic scores, not validated measures of underwriting skill.
- Missing credit score is treated as unknown for Character (50), not as a zero score.
- The benchmark's explanatory text for grades 1–4 currently contains the unrelated phrase “not a Coinbase trading-agent result”; that string is display copy and has no effect on scoring.
