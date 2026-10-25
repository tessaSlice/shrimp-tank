# Scorecard Logic

This document describes the scorecard implemented in the current code. It is a deterministic teaching simulation, not a real credit decision, a lender policy, or a forecast.

## Founder profiles: what is fictional and where it comes from

The playable founders are bundled catalog entries in [`backend/app/catalog.py`](../backend/app/catalog.py), tagged with 19 synthetic CRS persona IDs. Founder identities reuse the named synthetic personas; companies, loan requests, business stories, revenue, operating figures, collateral estimates, and market conditions are locally authored teaching data. The credit facts are bundled values and sentences, not reports fetched or normalized during gameplay. There are no real applicants or live credit-report pulls in the running game.

The profile is not generated when a player starts a pitch. All 19 cases are written directly into the catalog and passed through `_crs_presenter(case)` into the initially empty `PROFILES` list. The helper combines fixed profile values with locally written founder and business details, preserving explicit case IDs and capacity disclosures when supplied. `get_pitch(pitch_id)` returns a deep copy. When a session starts, the backend randomly selects pitch IDs from the full list, then `_start_pitch` copies the selected catalog entry into `GameSession.pitch`.

Grok may phrase a founder's dialogue using supplied facts, but it does not create or change the founder profile, five Cs assessment, benchmark, or deal outcome. The CRS MCP server informed development of the bundled examples; the running game does not call that server or the CRS API. The data-model guide lists [field origins and the CRS-backed facts represented by each persona](data-model.md#founder-field-origins). Under the project's documentation convention, borrower/scenario inputs without a directly available CRS source are labeled **AI synthesized**, including the fixed fictional business inputs and local credit proxies. This is an assumed origin classification; these inputs remain catalog literals at runtime, and Python calculates assessments and outcomes.

The profile has nine scalar inputs: `credit_score` (nullable), `derogatory_count`, `thin_file`, `severe_delinquency`, `monthly_free_cash_flow`, `monthly_existing_debt`, `owner_equity`, `collateral`, and `market_strength`. The separate `facts` dictionary contains one authored disclosure per C. `sandbox_expected_score` is catalog metadata, not a runtime comparison against an independent report. `benchmark_context` contains teaching prose but is not consumed by `assess` or `benchmark`. The repository does not retain the original report bodies, report IDs, score-model metadata, or an import/approval history sufficient to independently establish every bundled field's source.

### Current scenario inventory

The inventory below was calculated from the current catalog and `assess`/`benchmark` functions. It describes game cases, not a representative lending dataset or observed repayment outcomes. P14 is absent. The grade distribution is five grade 1 cases, ten grade 2, two grade 3, one grade 4, and one grade 5. Requests range from $105,000 to $225,000; scored personal-credit values range from 540 to 815, with three unscored profiles.

| Persona | Fictional business | Ask | Credit score | Game grade | Benchmark principal |
| --- | --- | --- | --- | --- | --- |
| P01 | Willow Creek Pharmacy | $185,000 | 790 | 1 | $185,000 |
| P02 | Orbit Forge Robotics | $220,000 | 815 | 1 | $220,000 |
| P03 | Brightline Pantry Labs | $145,000 | 660 | 4 | $65,000* |
| P04 | Cedar & Coast Provisions | $125,000 | None | 2 | $107,000 |
| P05 | Spindle & Loom | $160,000 | 540 | 5 | Walk away |
| P06 | Maplewood Circular Materials | $145,000 | 580 | 2 | $134,000 |
| P07 | Peachtree Fleet Services | $195,000 | 560 | 3 | $117,000* |
| P08 | Northstar Cold Chain | $210,000 | 690 | 2 | $166,000 |
| P09 | Front Range Fixture Works | $155,000 | 700 | 2 | $141,000 |
| P10 | Woodward Espresso Supply | $135,000 | 720 | 2 | $127,000 |
| P11 | Highland Route Couriers | $105,000 | 610 | 3 | $71,000* |
| P12 | Meridian Neighborhood Freight | $160,000 | None | 2 | $128,000 |
| P13 | Kingston Market Studio | $120,000 | 640 | 2 | $92,000* |
| P15 | Farragut Marine Repair | $175,000 | 740 | 1 | $175,000 |
| P16 | Brickell Solar Installations | $190,000 | 730 | 2 | $165,000 |
| P17 | Central Loop Packaging | $165,000 | 760 | 1 | $162,000 |
| P18 | Halsted Auto Glass | $130,000 | 650 | 2 | $119,000 |
| P19 | Solano Street Café | $225,000 | 770 | 1 | $220,000 |
| P20 | Ocean View Restoration | $115,000 | None | 2 | $110,000 |

*These four benchmark amounts are below the game's minimum permitted bid of 78% of the ask. They cannot be submitted as recommended, regardless of rate or security. The benchmark does not apply the API's bid floor or the player's remaining-capital limit. For example, P03's benchmark is $65,000 while its minimum bid is $113,100. This is a current disagreement between two rules, not a smaller facility the UI currently lets the player negotiate.

Selection uses `random.SystemRandom().sample` without replacement. There is no seed or fixed-queue request option. The selected IDs are saved in `pitch_queue`, so a persisted session retains its selection. Difficulty changes the human's capital, not the catalog, grade formulas, or AI investors' budgets. No repayments replenish the balance during a session. A case can therefore be unaffordable because of difficulty or earlier funding decisions; the score has no separate adjustment for lost opportunity. For example, P19's minimum bid is $175,500, above the $175,000 Hard starting balance.

### Where the profile and scorecard are stored

The full profile lives in `GameSession.pitch["profile"]` while the pitch is active. `_finish_pitch` copies it into the completed-pitch record in `GameSession.completed`. At the end of the last pitch, the backend calculates the scorecard and assigns it to `GameSession.scorecard`.

With the default SpacetimeDB session store, [`backend/app/spacetime_store.py`](../backend/app/spacetime_store.py) serializes the `GameSession` fields (except its in-process lock) into the `state_json` column of the private `game_session` table. That snapshot includes the active pitch, completed profiles, and scorecard. The separate `conversation_message` table stores dialogue rows and does not store the founder profile. If `SESSION_STORE=memory` is explicitly selected, session data instead lives only in backend process memory and is lost on restart. The table definitions are in [`spacetime/spacetimedb/src/index.ts`](../spacetime/spacetimedb/src/index.ts).

That saved state includes computed scorecard values, but it is not a complete versioned provenance record: the session schema has no dedicated fields for the application commit, Grok model/prompt revision, or resolved dependency versions. The current formulas below describe the inspected implementation, not a guarantee that a later code revision will reproduce every historical session. The [data-model guide](data-model.md) explains the persistence, configuration-history, and access boundaries; [the methodology's technical answers](methodology.md#questions-derived-from-that-stack) distinguish inspected code from local diagnostics and unverified deployment behavior.

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

Each component is rounded before the weighted sum is calculated; Python's `round` is also used for the total. For Character with an available score, the initial result and each subsequent thin-file/delinquency adjustment are clamped separately. Missing scores use 50 without those subsequent penalties. A no-file case, a stale unscored file, and an identity-mismatch case are therefore not separate numeric Character states.

The total is the rounded weighted sum: Character 30%, Capacity 25%, and Capital, Collateral, and Conditions 15% each. Grade cutoffs are: 1 / Prime at 84+, 2 / Strong at 68+, 3 / Moderate at 52+, 4 / Substandard at 36+, and 5 / Impaired below 36. Target rates for grades 1–4 are 6.5%, 9%, 12.5%, and 17%; grade 5 has no target rate.

`benchmark` turns that assessment into a comparison offer. Grade 5 maps to “walk away.” For other grades, it calculates a capacity fraction as `clamp((DSCR − 0.75) / 1.45, 0.35, 1)` and a collateral fraction as `clamp(collateral / ask + 0.25, 0.4, 1)`. It takes the lowest of the ask, ask multiplied by either fraction, rounds down to $1,000, applies a $25,000 minimum, and uses the grade's target rate. This is the game's rules-based comparison point; it is not an offer made by a bank or by Grok.

### What the five Cs calculation does not evaluate

- The assessment always reads the complete hidden profile, regardless of what the player or investors have disclosed. Question quality and coverage do not change the borrower's grade.
- The payment estimate uses the original request, not the player's proposed amount, rate, or term. There is no amortization calculation or recomputed DSCR for a smaller, higher-rate, or longer-term offer.
- Free cash flow is an authored scalar described as remaining after operating costs, with existing debt added separately in the denominator. Taxes, owner draws, maintenance investment, accounting periods, seasonality, and refinancing adjustments are not separately modeled. P03's warning about one-time revenue does not reduce its $12,000 numeric cash-flow input.
- Capital is owner equity divided by the requested loan, not verified current liquidity or total-project capitalization. Narrative reserves are not separate inputs. Previously invested money can therefore produce a strong Capital score despite a warning about limited cash.
- Collateral is an authored support/resale estimate. There is no asset register, lien search, valuation date, liquidation-cost calculation, or proof that security can be perfected.
- Conditions is the fixed `market_strength` scalar. Customer concentration, contract duration, or a market warning affects dialogue but is not parsed into an additional financial stress.
- There is no minimum-DSCR gate, identity-verification state, or manual-review action. Other component strength can compensate for weak capacity. P12's identity-mismatch narrative is not an enforced verification hold; its profile receives grade 2 and an otherwise eligible offer can be accepted.

The constants and weights are executable teaching choices. The repository supplies no empirical calibration or derivation that makes the grade a default probability, a bank classification, or an independent assessment of a real applicant.

## Offer eligibility and founder selection

The rules are in [`backend/app/main.py`](../backend/app/main.py), not in Grok. A human offer must fit the request-model bounds, remaining balance, and 78%–150% of the ask. `offer_is_affordable` checks amount/rate/royalty limits and finite numbers; despite its name, it does not calculate the business's repayment affordability.

`_deal_candidate` then requires an amount of at least 78% of the ask, a rate at least the grade's target, and security for grade 4. Grade 5 has no target and cannot win. Marking an offer secured does not verify sufficient collateral or reduce the assumed loss percentage. The game has no draw/repayment accounting for a revolving line, equity instrument, covenants, or staged advances, even when narrative descriptions suggest those structures.

Among eligible pending offers, `_founder_preference` maximizes:

```text
100 × min(1, amount / ask)
− 2.1 × max(0, rate − opening_rate)
− 1.5 × royalty
```

Term and security are absent from that preference. There is no further borrower repayment test or minimum utility required to accept the best eligible offer. Ties follow offer-list order. An eligible offer can close a pitch in round 1; three rounds is a maximum, not guaranteed investigation time.

AI offers begin in round 2 and use the full hidden assessment. Kevin's per-pitch cap is $185,000 and maximum grade 3, Lori's $145,000 and grade 4, and Mark's $230,000 and grade 3. Rates are target plus 1.25, 2.0, or 0.75 percentage points respectively; Mark also requests 0.5% royalty. AI terms are 36 months, secured at grade 3 or worse. These fixed caps are reused each pitch, rather than depleted like the player's balance. The first eligible investor is selected in round 2 and the last remaining eligible investor in round 3; Grok enthusiasm does not choose the bidder or terms.

Pass generates another table exchange and leaves any existing human offer pending. A replacement human offer withdraws the previous one. I'm Out withdraws the human's pending bids and generates all remaining rounds before the engine selects among the other offers. It does not end the session just because the human leaves.

## “Decision Fit” vs. “Underwriting Instinct”

These are separate measures, and neither is the five Cs total.

### Decision Fit

For each pitch, `score_session` assigns a heuristic decision score from 0 to 100. The rules differ by outcome:

- If the player wins the deal, use `max(0, 100 − int(abs(player_rate − benchmark_rate) × 8))`. The integer conversion truncates the rate-gap penalty. The code contains a further 20-point grade 5 penalty and a 25-point grade 4 below-target-rate penalty, but both conditions are blocked by the current eligibility rules and cannot occur through normal accepted offers.
- If the pitch is grade 5, award 100 points for the benchmark walk-away case. Grade 5 offers cannot currently win under the deal-eligibility rule.
- If nobody wins and the pitch is grade 1 or 2, award 65 points; if it is grade 3 or 4, award 82.
- If another investor wins, award 78 points.

**Decision Fit** is the rounded average of those per-pitch scores. The name describes a teaching heuristic: this is not a statistical accuracy rate and it is not a comparison against real loan outcomes.

The benchmark's suggested amount is not compared with the player's amount in Decision Fit. Term, collateral verification, royalties, number of questions, and coverage are not directly rewarded either. Those terms can affect eligibility, which investor wins, or the separate profit contribution. The grade and winner branches mean the same decision process can receive different points when a competing investor wins. There is no learner-knowledge model or reasoned-decision assessment.

### Underwriting Instinct

The score in the circle is `overall_score`, labeled “Underwriting Instinct.” It combines Decision Fit with a game-profit score:

1. For each deal won by the player, calculate expected game P&L as `principal × (annual rate / 100) × (term in months / 12) − principal × assumed loss rate`.
2. The assumed loss rate is grade-based: 1%, 4%, 12%, 30%, or 75% for grades 1 through 5. Pitches not funded by the player contribute zero expected P&L. The formula does not include royalties or model amortized payments.
3. Convert total expected P&L to a 0–100 profit score: `clamp(round(50 + total expected P&L / starting capital × 100), 0, 100)`.
4. Calculate **Underwriting Instinct** as `round(Decision Fit × 0.80 + profit score × 0.20)`.

Starting capital is $350,000 for Easy, $250,000 for Medium, and $175,000 for Hard. The displayed projected ending capital is starting capital plus total expected game P&L. These values are illustrative mechanics, not return estimates.

The assumed loss fractions are not documented estimates of probability of default or loss given default with a defined time horizon. They are subtracted once while interest scales with term. Security and royalties do not change this loss calculation, and the formula omits amortization, default timing, missed interest, recoveries, funding costs, and discounting. Raising the rate or extending the term can improve game P&L without changing the assessed capacity. Per-pitch P&L is rounded for display; aggregation and the profit-score calculation use the accumulated unrounded values. Scores are also sensitive to starting capital, scenario mix, and order, so cross-difficulty or cross-session skill comparisons are not established.

### Reproducible offline examples

Local checks used FastAPI's in-process test client with `SESSION_STORE=memory`, an empty Grok key, and a fixed pitch queue. They did not call Grok or SpacetimeDB and do not establish deployed behavior.

- P08: Immediately fund $210,000 at 9% for 36 months without asking a question. The game accepts the offer and produces Decision Fit 100. P&L is `$210,000 × .09 × 3 − $210,000 × .04 = $48,300`; the profit score rounds to 69 and Underwriting Instinct to 94. Investigation skill is not required for those points.
- P05: Pass all three rounds without a player question. No deal is made. Decision Fit is 100, profit score is 50, and Underwriting Instinct is 90. Declining a grade 5 case can earn a high score without demonstrating inquiry or financial analysis.
- P03: Submitting its $65,000 benchmark principal receives HTTP 422 because the minimum bid is $113,100.
- P12: An offer of $160,000 at 9% is accepted despite the unresolved identity-mismatch sentence. There is no verification-hold gate in the decision path.

## When the scorecard is calculated and shown

The final scorecard is calculated in `_finish_pitch` when the last pitch closes. It is kept off the public session response during `pitch_review`, while the founder's decision is still hidden. After the player reveals that decision, the final pitch result contains the scorecard; the browser displays it when the player selects the continue action from that last result. The rendering and labels are in [`frontend/src/main.ts`](../frontend/src/main.ts).

There is one route inconsistency in the current implementation: `GET /api/sessions/{session_id}/scorecard` requires phase `complete`, but the backend's final-pitch flow does not set that phase, and the browser does not call this endpoint. The working UI path reads `scorecard` from the regular session response instead. This is an endpoint/phase mismatch, not part of the score calculation.

The review step withholds `result` and `scorecard`, not every outcome signal. `_finish_pitch` already marks an offer accepted and deducts a winning human principal before returning review state; `_public_state` includes accepted offers and the changed balance. After reveal, the result JSON includes grade/risk label even though the intermediate result screen omits those labels. These are presentation/privacy boundaries of the existing response, not strict concealment until the final scorecard. The offline example above confirmed both the early accepted-offer/balance signals and the scorecard route's HTTP 409 after final reveal.

## Scope and caveats

- This rubric is hand-authored and not calibrated against repayment results or lender policy.
- “Decision Fit” and “Underwriting Instinct” are game labels for heuristic scores, not validated measures of underwriting skill.
- Missing credit score is treated as unknown for Character (50), not as a zero score.
- The benchmark's explanatory text for grades 1–4 currently contains the unrelated phrase “not a Coinbase trading-agent result”; that string is display copy and has no effect on scoring.
