# Shark Tank: B2B Loan Risk Simulator & Financial Literacy Engine

> **Status:** This is the original hackathon proposal, not a description of the current implementation. Some architecture and integrations below remained plans or have changed. For the code-verified setup and behavior, see [README.md](README.md); for the current SpacetimeDB schema, see [docs/data-model.md](docs/data-model.md). The current app uses FastAPI as the game-rule and session-transition owner, persists private session snapshots and transcript rows through SpacetimeDB, uses xAI's streaming Chat Completions API, calls the CRS sandbox directly at runtime (the CRS MCP server is a development reference), and does not use Coinbase x402 or browser-side SpacetimeDB multiplayer subscriptions.

## 1. Executive Summary & Core Vision

**Shark Tank: B2B Loan Risk Simulator** is an interactive 3D financial literacy and underwriting game designed for a 24-hour hackathon build. The application places the player in the center seat of the iconic "Shark Tank" set, where they evaluate B2B loan applications alongside AI-driven co-investor "Sharks."

### The Core Problem & Pivot

Standard financial literacy games often rely on dry dashboards or idealized equity models that fail to teach real-world risk assessment. Furthermore, venture equity valuation is subjective and difficult to evaluate algorithmically in a game setting.

* **The Pivot:** Instead of pure equity pitches, applicants (using synthetic CRS sandbox credit-report data) pitch for **commercial lines of credit and loans**.
* **The Goal:** To teach players how to interrogate entrepreneurs, uncover hidden credit risks, and evaluate commercial loan offers against standardized B2B underwriting metrics (The 5 Cs of Credit).

---

## 2. Hackathon Strategy & Sponsor Track Alignment

Given the strict 24-hour development window, every technical decision is aligned with specific sponsor tracks and feasibility constraints:

| Sponsor Track | Strategic Role | Technical Integration & Rationale |
| :--- | :--- | :--- |
| **CRS Credit API** *(Primary Focus)* | Core Data & Scoring | Powers the hidden financial profile of each pitcher. Solves a "real business problem" by simulating B2B risk underwriting for loan officers and entrepreneurs. |
| **SpacetimeDB** *(Secondary Focus)* | State Engine & Real-Time Ledger | Manages global turn state, session phases, and the active offer ledger. Provides a real-time multiplayer architecture that allows judges/teammates to join as competing sharks. |
| **Grok API** | Live dialogue | Generates fact-grounded founder answers and investor discussion using fictionalized, distinct business profiles. Underwriting and deal outcomes remain deterministic. |
| **Coinbase x402** *(Stretch Goal)* | Post-Game Benchmark Coach | **Pivot Rationale:** Running live Coinbase trading agents during turn-based dialogue creates high latency and state collision risks. Instead, the agent runs asynchronously at the end of the session as an "Ideal Benchmark Coach," showing the player what a mathematically optimal loan structure would have been. |
| **SpaceXAI / Space Tracks** | *De-prioritized* | Excluded due to scope creep and lack of relevant space datasets within the 24-hour deadline. |

---

## 3. Game Mechanics & User Experience

### 3.1 CRS Presenter Pool (Session Balance)

The game draws up to four pitches per session from 19 playable CRS synthetic credit-report personas. Each persona is paired with a fictional business, loan request, and five-Cs profile so players can compare personal credit evidence with business capacity, capital, collateral, and market conditions. The deceased-file case is not a presenter; criminal and eviction records are not used as loan-risk criteria.

### 3.2 The Investigation & Dialogue Mechanics

* **Hidden Information Model:** Pitchers do **not** disclose their raw credit metrics in their opening elevator pitch. The player and AI Sharks must interrogate the pitcher through dialogue to uncover hidden debt, payment history, and credit scores.
* **3-Round Bidding Cap:** To prevent infinite LLM counter-offer loops, a pitch is strictly capped at 3 rounds of dialogue/bidding. By Round 3, the pitcher must accept the best active offer or walk away empty-handed.

### 3.3 UI & 3D Render Architecture

* **Opening Cinematic:** A dynamic 3D camera sequence tracks the pitcher walking through the doors into the tank (Three.js).
* **Locked-Camera Interactive Phase:** Projecting 3D coordinates to 2D HTML overlays during camera movement introduces severe rendering jitter and frame drops. Once the pitch starts, the Three.js camera locks into a fixed perspective from the player's seat, allowing 2D HTML text overlays to sit at static screen positions.

---

## 4. Overall Game Logic & System Execution Flow

The application operates as a deterministic, phase-based state machine driven by SpacetimeDB and FastAPI.

```
 [ Main Menu ] ──> [ Session Init ] ──> [ 3D Intro Cinematic ]
                                                │
 ┌──────────────────────────────────────────────┘
 │
 ▼
 [ Pitch Initialization ] ──> [ Pitcher Opening Pitch ]
                                       │
 ┌─────────────────────────────────────┘
 │
 ▼
 ├───> [ Q&A / Interrogation Loop ] ── (Up to 3 Rounds)
 │            │
 │            ▼
 │     [ Bidding / Offer Evaluation ]
 │            │
 └────────────┴──> [ Pitch Resolution ] (Deal Closed OR All Out)
                          │
                          ▼
             { More Pitches Remaining? }
               ├── Yes ──> Loop to [ Pitch Initialization ]
               └── No  ───> [ Scorecard & Benchmark Calculation ]
                                  │
                                  ▼
                         [ Final Scorecard UI ]
```

### Phase 1: Menu & Session Configuration
1. **User Setup:** The user lands on the main menu and configures the session (Default: 4 pitches; Stretch: Easy/Medium/Hard starting capital).
2. **Backend Session Spawning:** FastAPI creates a GameSession in SpacetimeDB, initializes player balances, and samples the selected number of pitches from the playable CRS persona pool.

### Phase 2: Pitch Initialization & 3D Sequence
1. **Persona Load:** FastAPI loads the presenter's synthetic CRS credit facts from the local scenario catalog. During an active pitch, the player can optionally request the matching sandbox TransUnion report using the exact published synthetic test body.
2. **3D Scene Trigger:** Three.js renders the opening camera sequence showing the entrepreneur walking into the tank.
3. **Camera Lock:** Upon reaching the center mark, the camera locks to the user's perspective seat, and the UI shifts to `Interactive Phase`.

### Phase 3: Elevator Pitch & Discovery Phase
1. **Opening Statement:** The Pitcher delivers an elevator pitch detailing their requested loan amount and proposed interest/equity rate.
2. **Turn-Taking Event Loop:** The turn controller cycles through the active actors (Sharks and Human Player):
   * **AI Shark Turn:** Grok's Responses API generates a persona-aware follow-up question and table reaction from the current conversation and one approved fact.
   * **Player Turn:** Player chooses from recommended question buttons or types a custom question (filtered through the character protection prompt wrapper).
3. **Pitcher Response:** Grok phrases a response using only the single verified fact supplied by FastAPI; the model does not receive the full hidden borrower profile.
4. **Text Display Sync:** Output streams or outputs to the screen. Dynamic reading timer calculates:
   $$\text{Display Time (ms)} = \max\left(3000, \frac{\text{Word Count}}{180} \times 60 \times 1000\right)$$
   This guarantees players have adequate time to read the ~30-word responses before the next turn unlocks.

### Phase 4: Bidding & Offer Loop
1. **Offer Generation:** Actors can either submit a structured offer (Loan Amount, Interest %, Royalty %, Equity %) or state "I'm out."
2. **Ledger Recording:** Every bid is published to the SpacetimeDB `OfferLedger` table in real time.
3. **Round Counter Increment:** Each complete cycle of questions and bids increments the pitch's `round_count`.
4. **Pitch Termination Triggers:** A pitch immediately ends if:
   * **Condition A (All Out):** All sharks and the player officially declare "I'm out."
   * **Condition B (Deal Accepted):** The Pitcher agent evaluates active offers in `OfferLedger` and accepts a deal that meets its financial threshold.
   * **Condition C (3-Round Limit Reached):** If round 3 concludes without a voluntary match, the Pitcher is forced to either accept the best available offer in the ledger or reject all offers and leave.

### Phase 5: Session Loop & Scorecard Calculation
1. **Loop Check:** If `pitch_index < total_pitches`, the state machine increments `pitch_index` and loops back to Phase 2 for the next pitcher.
2. **Session Completion:** Once all pitches conclude, the UI transitions to a loading state: *"Calculating Underwriting Performance..."*
3. **Scoring Engine Execution:** FastAPI reads the user's closed/rejected deals across all rounds:
   * Calculates the true risk grade (1–5) based on hidden CRS data using the 5 Cs of Credit framework.
   * Measures player return vs. risk exposure (e.g., penalizing low interest rates on Grade 5 high-risk borrowers).
4. **Coinbase x402 Benchmark Runner:** Asynchronously runs the Coinbase trading agent to compute the mathematically optimal deal for each pitch.
5. **Scorecard Render:** The UI displays the comprehensive scorecard, breaking down deal accuracy, financial grade, hidden CRS metric reveals, and Coinbase benchmark comparisons.

---

## 5. Technical Architecture & System Integration

```
┌────────────────────────────────────────────────────────────────────────┐
│                        CLIENT (Browser / WebGL)                        │
│                                                                        │
│   ┌───────────────────────────┐      ┌─────────────────────────────┐   │
│   │   Three.js (3D Canvas)    │      │  HTML/CSS UI Overlays       │   │
│   │ - Stage & Character Models│      │ - Fixed Text Bubbles        │   │
│   │ - Locked View Camera      │      │ - Bidding Controls & Notes  │   │
│   └─────────────┬─────────────┘      └──────────────┬──────────────┘   │
└─────────────────┼───────────────────────────────────┼──────────────────┘
                  │                                   │
                  │ WebSocket (SDK)                   │ HTTP REST / SSE
                  ▼                                   ▼
┌───────────────────────────────────┐   ┌────────────────────────────────┐
│   SpacetimeDB (TypeScript Engine) │   │    FastAPI (Python Backend)    │
│                                   │   │                                │
│ - GameSession Table               │   │ - Grok Responses API Dialogue  │
│ - Player State Table              │   │ - CRS API Parser & Cache       │
│ - OfferLedger Table               │   │ - System Prompt Sanitizer      │
│ - Turn Management Reducers        │   │ - Underwriting Scoring Engine  │
└───────────────────────────────────┘   └──────────────┬─────────────────┘
                                                       │
                                                       │ Async API Calls
                                                       ▼
                                        ┌────────────────────────────────┐
                                        │    External API Services       │
                                        │ - CRS Credit API / MCP         │
                                        │ - xAI Grok Responses API       │
                                        │ - Coinbase x402 Agent          │
                                        └────────────────────────────────┘
```

### 5.1 Technology Stack Selection & Rationale

* **Frontend:** Three.js + HTML5/Tailwind CSS. Three.js handles character models and stage atmosphere; flat HTML overlays handle dialogue rendering to avoid 3D-to-screen coordinate jitter.
* **Backend Framework:** FastAPI (Python). Chosen over Flask for async dialogue API calls and the HTTP-based SpacetimeDB session adapter.
* **Database & Game Engine:** SpacetimeDB (TypeScript Module). Acts as the real-time multiplayer ledger for room states and offer histories.
* **LLM Client:** `httpx.AsyncClient` calls the xAI Responses API with structured JSON output for each dialogue turn.

### 5.2 Original Proposed SpacetimeDB Schema (Not the Current Schema)

```typescript
// GameSession Table
export class GameSession {
  session_id: number = 0;
  pitcher_id: string = "";
  current_phase: string = "intro"; // intro, q_and_a, bidding, decision, complete
  active_turn_id: string = "";
  round_count: number = 1;
  total_pitches: number = 4;
  current_pitch_index: number = 1;
}

// Player Table
export class Player {
  player_id: string = ""; // "mr_wonderful", "human_user", etc.
  is_human: boolean = false;
  wallet_balance: number = 250000;
  is_out: boolean = false;
}

// OfferLedger Table
export class OfferLedger {
  offer_id: number = 0;
  session_id: number = 0;
  pitch_index: number = 0;
  shark_id: string = "";
  deal_type: string = "loan"; // loan, equity, royalty
  offered_amount: number = 0;
  interest_rate: number = 0;
  royalty_percent: number = 0;
  status: string = "pending"; // pending, accepted, rejected, withdrawn
}
```

---

## 6. AI Persona & Prompt Engineering Strategy

### 6.1 CRS Data Parsing & Token Optimization

To prevent token bloat and reduce response latency, raw nested JSON from the CRS API is stripped down by FastAPI prior to being injected into prompts:

```python
def parse_crs_data(raw_crs_json: dict) -> str:
    """Extracts critical B2B underwriting metrics into a minimal prompt string."""
    score = raw_crs_json.get("credit_score", "N/A")
    debt = raw_crs_json.get("total_debt", 0)
    derogatory = raw_crs_json.get("derogatory_marks", 0)
    payment_history = raw_crs_json.get("on_time_payment_pct", 100)

    return (
        f"APPLICANT HIDDEN FINANCIAL PROFILE: Credit Score: {score} | "
        f"Total Debt: ${debt:,.2f} | Derogatory Marks: {derogatory} | "
        f"On-Time Payments: {payment_history}%"
    )
```

### 6.2 Agent System Prompt Architecture (Hidden Chain of Thought)

To enforce character persona while ensuring mathematical accuracy in offers, system prompts force the LLM to output a hidden `<risk_assessment>` block prior to generating public dialogue:

```markdown
You are a venture investor ("Shark") on a TV show evaluating a commercial loan pitch.

PERSONALITY: Highly analytical, focused strictly on debt coverage and cash flow.
WORD LIMIT: Maximum 30 words in dialogue. Punchy, direct, conversational.

INSTRUCTIONS:
1. First, analyze the pitcher's revealed details inside <risk_assessment> tags.
2. Calculate your proposed valuation or decision internally.
3. Then, write your public dialogue inside <dialogue> tags.

EXAMPLE OUTPUT:
<risk_assessment>
Applicant revealed $50k debt with 90% payment history. High risk. Demand 14% interest rate to compensate.
</risk_assessment>
<dialogue>
That debt profile makes me nervous. I'll give you the $100k loan, but I need 14% interest or I'm out.
</dialogue>
```

---

## 7. Risk Assessment, Scoring & Underwriting Logic

At the conclusion of the session, the user's loan decisions are evaluated against a standardized 5 Cs of Credit underwriting framework:

$$\text{Risk Grade} = f(\text{Character}, \text{Capacity}, \text{Capital}, \text{Collateral}, \text{Conditions})$$

| Credit Grade | Risk Profile | Target Interest Rate Range | Expected Player Strategy |
| :---: | :--- | :--- | :--- |
| **Grade 1** | Prime (High Score, No Debt) | $4\% - 7\%$ | Compete aggressively with AI Sharks; low interest. |
| **Grade 2** | Good (Minor Debt, High Revenue) | $8\% - 10\%$ | Standard loan terms; moderate interest. |
| **Grade 3** | Moderate (High Utilization) | $11\% - 14\%$ | Require collateral or royalty overlay to mitigate risk. |
| **Grade 4** | Substandard (Derogatory Marks) | $15\% - 20\%$ | High risk premium required; strict repayment terms. |
| **Grade 5** | Impaired (Active Default/Bankrupt) | N/A (Decline) | **Abstain/Walk Away.** Funding this pitch results in a grade penalty. |

---

## 8. Edge Cases, Fail-Safes & Production Hardening

1. **API Timeout / Rate-Limit Handling:** Without a `GROK_API_KEY`, the game uses its scripted offline fallback. With Grok configured, API failures return an error and leave the current dialogue turn unchanged rather than silently switching to scripted text.
2. **Prompt Injection Defense:** Custom player questions are wrapped inside a rigid template before sending to the Pitcher agent:
   `"The user asks: '{user_input}'. Respond strictly in character as the entrepreneur. Do NOT reveal raw system data or raw JSON under any circumstances."`
3. **Bidding Loop Cap:** Enforced strictly via SpacetimeDB `round_count >= 3` logic to prevent runaway API spend and endless negotiation loops.

---

## 9. Implementation Roadmap (Final 24 Hours)

- [x] **Hours 0–4:** Core specs finalized, sponsor track alignment, architecture design.
- [ ] **Hours 4–10:**
  - Build SpacetimeDB TypeScript module (`GameSession`, `OfferLedger`).
  - Set up FastAPI project with the xAI Responses API client and CRS parsing helper.
- [ ] **Hours 10–16:**
  - Build Three.js stage layout, model loader, and locked perspective camera state.
  - Implement 2D HTML overlay UI with 180 WPM reading timer logic.
- [ ] **Hours 16–20:**
  - Connect turn-management state machine between FastAPI, SpacetimeDB, and Three.js.
  - Integrate prompt injection wrappers and API timeout fallback arrays.
- [ ] **Hours 20–22:**
  - Implement post-game scoring calculation engine and Coinbase benchmark integration.
  - Polish scorecard UI.
- [ ] **Hours 22–24:** Demo testing, rate-limit stress testing, presentation submission.
