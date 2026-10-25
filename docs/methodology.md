# Shrimp Tank: Methodology Questions and Answers

## Purpose and scope

This is a focused review of the current fictional loan-negotiation game. It retains 73 existing questions and answers each directly below its bullet. It does not add new questions. All 18 topical sections remain; repetitive questions, detailed future integrations, vendor edge cases, and unsupported hypothetical lending workflows were pruned. Retained question IDs are unchanged.

The application code in the current checkout is the source of truth. Comments and historical proposals describe intent only when the executable path supports them. The original documentation review inspected the repository at commit `2580732`; the later paper-portfolio update also checked Coinbase's official public-candles documentation. Local offline diagnostics are identified separately from code inspection. Live Grok behavior, deployed SpacetimeDB recovery, production revisions, and assistive-technology behavior were not tested.

## Documentation maintenance for methodology answers

Whenever an answer in this file is added or materially revised, review the relevant existing guides, inspect the corresponding code, and update affected documentation to agree with that code. Put detailed calculations and case facts in [Scorecard Logic](scorecard-logic.md), state/schema details in [SpacetimeDB Data Model](data-model.md), and setup/gameplay explanations in [README](../README.md). Keep the [proposal](../shark_tank_project_specs.md) clearly historical and its current-status comparison accurate. An already-congruent file needs no cosmetic edit.

This requirement applies to answering this file, not to unrelated tasks or question-only editing. Do not add more questions. Keep unknown design rationale and missing evidence explicit rather than inventing an answer. The previously removed grounding, independent-validation, fairness/privacy, and demonstration categories remain removed.

## Verified technology-stack context

| Area | Technology identified | Repository reference |
| --- | --- | --- |
| Browser application | TypeScript, Vite, Three.js | [Frontend package](../frontend/package.json) |
| API service | Python, FastAPI, Uvicorn, Pydantic request models | [Dependencies](../backend/requirements.txt), [API imports and setup](../backend/app/main.py) |
| Outbound API communication | HTTPX; xAI Grok Chat Completions with streaming and JSON Schema response formatting | [Dialogue integration](../backend/app/agents.py) |
| Public market data and investor paper trading | Coinbase Advanced Trade public candles API; deterministic Python paper-portfolio rules | [Portfolio agent](../backend/app/portfolio_agent.py), [Coinbase endpoint docs](https://docs.cdp.coinbase.com/api-reference/advanced-trade-api/rest-api/public/get-public-product-candles) |
| Game-state persistence | SpacetimeDB TypeScript module and Python HTTP adapter; session and conversation storage | [Module package](../spacetime/spacetimedb/package.json), [Adapter](../backend/app/spacetime_store.py), [Data model](data-model.md) |
| External credit-data source | CRS Credit API sandbox; synthetic consumer-credit reports in CRS Standard Format from TransUnion, Equifax, and Experian | Attached `crs-calhacks` resources: `crs://docs/products`, `crs://guides/credit_report`, `crs://schemas/credit_report` |
| CRS access and development tooling | Model Context Protocol (MCP), through `@crscreditapi/crs-calhacks-mcp-server`; persona fixtures, product guides, and API schemas | [Package listing](https://www.npmjs.com/package/@crscreditapi/crs-calhacks-mcp-server), attached `crs://docs/quickstart` resource |

This identifies components and interfaces, not the health of a deployed service, its active credentials or model, or the correctness of its financial decisions. The distinction between development tooling and gameplay dependencies is itself examined below.

### CRS source data versus the game database

The attached service calls itself **CRS Credit API**; this is the service referred to as the "CSR database" in the review request. Its MCP resources describe access to synthetic credit-data fixtures and bureau-report APIs. That establishes a source-data service and an MCP access layer, not the identity of CRS's underlying database engine or direct access to its internal tables. SpacetimeDB is the separately documented game-state database.

The quickstart, products overview, credit-report integration guide, and API schema were read through the attached MCP server. These are interface and source-data references; they do not establish that a particular raw report was retrieved, retained, or used to calculate a game result. The answers below investigate that evidence chain without equating source availability with runtime integration.

### Questions derived from that stack

These retained answers distinguish repository configuration, local diagnostics, and unverified deployment state. Detailed provider-schema, retry/cancellation, and security questions were pruned; their already established implementation limits remain in the README and data-model guide.

- TECH-01: Which resolved frontend, Python, database-module, and CLI versions run in the judged deployment, and how are they tied to one reproducible release?

  **Answer:** The checked-in [frontend lockfile](../frontend/package-lock.json) resolves Three.js `0.186.1`, its types `0.186.0`, TypeScript `7.0.2`, and Vite `8.3.5`. The [database-module lockfile](../spacetime/spacetimedb/package-lock.json) resolves SpacetimeDB `2.13.0` and its separate TypeScript compiler `5.6.3`. These are reproducible dependency selections when installed with `npm ci`.

  Local diagnostics found Python `3.14.4`, FastAPI `0.162.0`, Pydantic `2.14.1`, Uvicorn `0.54.0`, HTTPX `0.28.1`, and python-dotenv `1.2.4` in `.venv`; the shell reported Node `22.22.1`, npm `9.2.0`, and SpacetimeDB CLI `2.13.0`. These describe this machine, not a verified Render deployment. [Python requirements](../backend/requirements.txt) specify version ranges rather than an exact resolved lockfile, so a fresh backend install can resolve differently.

  The [deployment helper](../scripts/deploy-render.sh) requires a clean checkout matching its upstream and prints the Git SHA. It then publishes the database module and triggers Render hooks; it does not send an explicit commit SHA in the hook request or verify the resulting service revisions. No deployment manifest ties the served frontend, backend dependency resolution, database publication, and CLI version to one verified release. The judged deployment's exact versions therefore remain unconfirmed.

- TECH-02: Which environment settings select the API endpoint, Grok model, and persistence mode, and how is the active configuration recorded without exposing secrets?

  **Answer:** The browser uses build-time `VITE_API_BASE`, defaulting to `http://localhost:8000`. Backend settings are `GROK_API_KEY`, `GROK_MODEL` (default `grok-4.3`), `GROK_BASE_URL` (default `https://api.x.ai/v1`), `GROK_REASONING_EFFORT` (default `none`), and `GROK_TIMEOUT_SECONDS` (default `3600`). The API URL helper targets `/chat/completions`, including when the configured base ends in `/responses`. `SESSION_STORE=memory` selects process memory; otherwise the adapter selects SpacetimeDB using `SPACETIMEDB_URI`, `SPACETIMEDB_DATABASE`, and a server token. Locally it can obtain that token from the CLI. `FRONTEND_ORIGINS` configures allowed browser origins. Sources: [templates](../.env.example), [browser configuration](../frontend/src/main.ts), [Grok configuration](../backend/app/agents.py), and [store selection](../backend/app/spacetime_store.py).

  The API reports provider/store labels through `/api/config`, and public sessions contain `ai_mode`. These are not a full configuration history: the model, prompt revision, code revision, and resolved dependencies are not recorded as dedicated session metadata. `.env` files are ignored and the browser should receive only public configuration. This answer lists names and defaults; private environment values were not inspected.

- TECH-03: Do health and configuration indicators establish successful provider and database operations, or only that a service is running with particular settings?

  **Answer:** They establish service responsiveness and configuration selection. In [the API](../backend/app/main.py), `/api/health` returns `ok: true`, a service name, and the selected database label. `/api/config` reports `ai_provider` and `database`. Provider selection in [the dialogue module](../backend/app/agents.py) checks whether the API-key environment variable is nonempty; it does not validate the key. Constructing the SpacetimeDB adapter requires a token but makes no database connectivity request. Neither endpoint performs a Grok generation or a database read/write. A successful status response therefore does not demonstrate that credentials, the configured model, the published database, or its permissions work.

- TECH-04: What do Pydantic's request models actually guarantee about types, coercion, numeric bounds, and finite values before financial rules receive an input?

  **Answer:** FastAPI uses the three [Pydantic request models](../backend/app/main.py) to validate session creation, questions, and decisions. They constrain pitch count to 1–4, difficulty and action to listed choices, question length to 2–400 characters, supplied amount to $25,000–$750,000, supplied rate to 0–40, royalty to 0–12, and term to 6–84 months. Defaults are filled in, and model-validation failures produce HTTP 422 responses.

  These models do not enable strict typing or rejection of extra fields. A local diagnostic using the actual model definitions confirmed conversion of numeric strings to numbers and `"false"` to a boolean; an unrecognized field was ignored. It also confirmed rejection of NaN and infinity for the bounded rate field. This is consistent with [Pydantic's default coercion behavior](https://docs.pydantic.dev/latest/concepts/strict_mode/). Amount and rate remain optional at the model level; the offer handler separately requires them when the action is `offer`. Phase eligibility, available capital, and other game constraints are also checked in backend logic. These are request-validation guarantees, not validation of the financial method or every object loaded from storage.

- TECH-06: Can synchronous database calls block FastAPI's asynchronous request processing, and what happens to turn timing and consistency under concurrent use?

  **Answer:** Yes. [The persistence adapter](../backend/app/spacetime_store.py) uses synchronous `httpx.post`, and [async API routes](../backend/app/main.py) call its `get` and `put` methods directly. There is no thread offload around those calls. A database request can therefore block that worker's event loop and delay other requests or streaming output handled by the same worker. FastAPI does not automatically move directly called synchronous utility functions into its thread pool. [FastAPI concurrency documentation](https://fastapi.tiangolo.com/async/).

  Per-session `asyncio.Lock` objects serialize cooperating mutation handlers within one process, including the streamed question handler. Across processes, the [database reducer](../spacetime/spacetimedb/src/index.ts) compares `expectedUpdatedAt` with the stored version before committing the snapshot and transcript rows together. This rejects stale writes; it does not coordinate the preceding Grok requests or eliminate their cost, and the adapter does not automatically merge or retry a rejected write. No load test or concurrency failure test was performed for these answers, so timing impact and recovery behavior are code-based expectations rather than measured results.

- TECH-08: For the FastAPI-to-browser update path documented in the data-model guide, which streaming transport is used, and what reconnect and ordering guarantees does it actually provide?

  **Answer:** [The browser's `streamQuestion`](../frontend/src/main.ts) makes a `fetch` POST with a JSON question and reads the response through a `ReadableStream` reader and `TextDecoder`. [FastAPI](../backend/app/main.py) returns `text/event-stream` frames named `message_start`, `delta`, `progress`, `complete`, or `error`. This question-turn path uses SSE framing over fetch, not `EventSource` or WebSocket. A separate WebSocket endpoint broadcasts saved session snapshots to other clients in the LAN shared-session preview; neither path subscribes to SpacetimeDB.

  The client processes frames sequentially on that connection. It has no SSE event IDs, `Last-Event-ID` resume path, automatic reconnect, or cross-connection deduplication. It accepts the saved public session in `complete` as the result; an incomplete stream throws an error. The current question UI uses speaker/progress updates during generation and ignores generated text deltas, then renders and plays the saved messages after completion. The separate transcript table is not the current browser delivery path, as described in the [data-model guide](data-model.md).

- TECH-09: With FastAPI documented as the game-rule owner, which checks also reside in the browser and database reducers, and what prevents duplicated rules from disagreeing about the same action?

  **Answer:** [The browser](../frontend/src/main.ts) manages presentation and convenience checks, including busy state, reading/playback locks, form constraints, and when controls are enabled. [FastAPI](../backend/app/main.py) validates request models, checks session state and balances, and invokes the backend game-rule functions. [Database reducers](../spacetime/spacetimedb/src/index.ts) enforce their argument types, primary-key operations, write-version checks, and the session/transcript transaction. They accept `stateJson` as a string and do not recompute Python game rules or validate every field inside that JSON.

  Backend acceptance is the authority for an API action, so changing a browser control does not remove backend checks. However, this is an architectural boundary rather than proof that every duplicated constraint agrees: the frontend has handwritten types and checks, and the database receives a serialized snapshot. There is no shared generated rules contract in these paths. Browser-only pacing rules are a concrete example of behavior the API does not independently enforce; see the [access control boundary](data-model.md#access-control-boundary).

- TECH-11: What bounds the total provider requests, tokens, and cost per pitch when validation retries, pass actions, player exit, reconnects, and any future benchmark request are included?

  **Answer:** Each live table exchange in [the Grok integration](../backend/app/agents.py) requests at most 420 output tokens per attempt. A founder-counter request requests at most 800. A question generates one structured exchange in one provider request; a nonmatching offer or pass starts one table exchange and can add a counter request for other pending offers. A nonmatching offer's direct founder reply is included in its table request, so that bid does not by itself add another request. A matching new human bid makes no Grok request. A table exchange that fails dialogue validation can be regenerated twice, for up to three requests. [Automatic discussion after exit](../backend/app/main.py) plans the remaining rounds before saving. If this round already had a question, it does not add a second table exchange for that round. Later rounds each add one exchange. Each planned round can also add one counter request. An HTTP 5xx response is retried with waits of 15, 30, 60, and then 120 seconds until Grok responds. Player-question validation and other HTTP errors are not retried by the dialogue regeneration path.

  A question is one provider request. A pass or nonmatching offer starts one table exchange, which may take up to three requests if its completed lines fail validation, plus one counter request for other pending offers. A nonmatching offer's direct founder reply is included in the table request, so that bid does not by itself add another request. A matching new human bid makes no Grok request. Exit plans every remaining round before saving and can add one counter request on each of those rounds. Dialogue requests ask for at most 420 output tokens per attempt; counter requests ask for at most 800. Each shark originates at most one bid and revises it at most once. The revision is a scripted personality reply, not another provider request, and it counts as a new offer for the quiet-offer clock. After the latest new offer, one more round is played, which bounds a pitch whose player stops submitting new offers. Three rounds with no offer at all also end the pitch. A player who submits a new offer every round resets that clock, so the quiet-offer rule does not by itself cap total requests. The exit fast-forward has a separate stop at round 24 if that planner has not already stalled. Ordinary offer and pass actions do not use that stop. Offline mode makes no Grok calls. HTTP 5xx responses are retried until Grok responds, so those calls have no attempt cap; each retry waits 15 seconds, then double that, up to 120 seconds. Other failures can be submitted again by the player without advancing a round. The server has no aggregate token or dollar budget, or per-user rate limiter. Input tokens are not bounded by `max_tokens`, and usage/cost is not recorded as a session ledger. There is no implemented benchmark-agent call in these paths; the proposal's future integration contributes no present request budget or verified cost estimate.

## 1. Claim and intended use

[README](../README.md) and [Scorecard Logic](scorecard-logic.md) were reviewed before inspecting the API's product description, `score_session`, and the browser's score labels. These establish implemented scope, not external evidence of learning or loan performance.

- CLAIM-01: Is the project claiming to teach questioning skills, simulate negotiations, reproduce a lender's policy, predict repayment, or recommend actual loans, and which claims have been independently evaluated?

  **Answer:** The implemented product is a fictional loan-negotiation teaching game. The browser presents pitches and dialogue; the backend applies a fixed rubric and scores play. Devices on a trusted LAN can join one shared session as separate investor seats: they share the pitch, AI investors, offers, and transcript, while player balance, exit state, turn, and scorecard are independent. Turns are sequential and the backend rejects out-of-turn actions. Browser IDs are not authenticated, and the live room hub is limited to one FastAPI process. The repository provides no repayment-outcome dataset, lender-policy certification, or learner-study results establishing predictive or educational accuracy. Its defensible demonstrated capability is executing and explaining these game rules. See the README's project boundaries and the scorecard guide's calculation limits.

- CLAIM-03: What does a "correct" loan decision mean here: policy compliance, affordable repayments, positive risk-adjusted return, borrower benefit, or agreement with the game's benchmark?

  **Answer:** Correctness currently means agreement with the game's eligibility, founder-selection, and scorecard rules. A seat's accepted offer is mainly rewarded for proximity to a target interest rate, while a separate illustrative-profit term affects the overall score. The code does not establish that an accepted deal is affordable to the borrower or optimal for a real lender. The benchmark is another output of the same rules, not an external ground truth.

- CLAIM-05: Which mechanics are entertainment choices inherited from Shark Tank, and which are intended to represent commercial lending practice?

  **Answer:** The investor-seat setting, personalities, quiet-offer clock, competitive offers, and reveal step are entertainment mechanics. Personal credit, cash-flow coverage, owner equity, collateral, and conditions are represented by simplified inputs. Offers contain loan principal, annual-rate input, term, revenue share, and a security flag; equity valuation, revolving draw accounting, document verification, and actual lending are absent. The original spec describes broader ambitions, not extra functioning products.

## 2. Data origin and founder-profile lifecycle

Context: [founder profiles](scorecard-logic.md#founder-profiles-what-is-fictional-and-where-it-comes-from). Executable sources: [catalog](../backend/app/catalog.py), `get_pitch`, `_start_pitch`, and `_finish_pitch` in [the API](../backend/app/main.py).

- DATA-01: For each field—founder identity, company, sector, revenue, cash flow, debt payments, credit score, owner equity, collateral, and market conditions—what is its original source?

  **Answer:** The runtime source for every founder is the literal catalog in `backend/app/catalog.py`. Entries associate synthetic CRS persona IDs and names with bundled credit facts; company identities, revenue, requests, cash flow, existing debt, owner equity, collateral, and market strength are authored scenario values. The catalog does not contain original source reports or field-level acquisition records that independently prove each source attribution. The scorecard guide now distinguishes synthetic founder identities from fictional business details.

- DATA-02: Which fields are supplied by CRS, written by developers, calculated from other fields, sampled randomly, or generated by Grok?

  **Answer:** At runtime, Grok generates dialogue strings, not the financial profile. All 19 entries use `_crs_presenter` to format fixed profile values and authored text into the common case shape in `PROFILES`. Explicit case IDs and capacity disclosures are preserved when supplied. Session initialization randomly samples case IDs; message/offer IDs are UUIDs. The five Cs, benchmark, offers, and results are calculated by Python. There is no runtime generation, sampling, or model update of company financial inputs. The code does not establish whether AI assisted with catalog authoring during development.

- DATA-03: What evidence corroborates the catalog-to-session profile lifecycle described in the scorecard guide, and how is any randomly sampled or newly generated content distinguished from the underlying profile?

  **Answer:** `create_session` saves a sampled `pitch_queue`; `_start_pitch` obtains a deep copy through `get_pitch` and assigns it to `GameSession.pitch`. The profile is copied into the completed record when the pitch closes and included in persistent snapshots. A local diagnostic confirmed that changing a returned pitch does not mutate the catalog. Revisiting the same catalog entry uses the same financial values unless code changes; dialogue wording can differ.

- DATA-08: How are narrative claims reconciled with numeric inputs when a founder describes one-time revenue, uncertain orders, limited reserves, or disputed credit information?

  **Answer:** Narrative and numeric fields are parallel authored inputs, not automatically reconciled statements. `assess` reads the numeric profile and never parses the five disclosure sentences or `benchmark_context`. For example, P03's one-time-revenue warning does not reduce the $12,000 cash-flow scalar. P12's identity warning does not create a hold state. The game can discuss a caution without imposing its implied underwriting restriction.

## 3. Initial dataset and session selection

Context: [scenario inventory](scorecard-logic.md#current-scenario-inventory). Sources: [catalog](../backend/app/catalog.py), `create_session` and capital/balance handling in [the API](../backend/app/main.py). Inventory values were calculated locally from the actual case objects and rubric.

- SET-01: What versioned inventory corroborates the playable persona count described in the scorecard guide, and which source cases have been excluded or combined?

  **Answer:** The catalog contains one entry for each persona P01–P13 and P15–P20: 19 cases, with P14 absent. Four retain descriptive legacy IDs and the other 15 use lowercase persona IDs. They are bundled with the source revision rather than loaded from a versioned case-import table. The current case inventory and calculated grades are listed in the scorecard guide.

- SET-03: What distributions of credit quality, industries, loan sizes, cash-flow strength, business age, and missing-data conditions does the dataset cover?

  **Answer:** The current authored cases request $105,000–$225,000 and carry personal scores of 540–815 plus three unscored profiles. Applying the actual rubric produces grades 1/2/3/4/5 in counts 5/10/2/1/1. The cases span named sectors but do not provide a sampled business population, separate evaluation set, or observed defaults. These figures describe the game catalog; they do not establish representativeness or lending-model performance.

- SET-05: How are scenarios selected and ordered within a session, and can a judge reproduce the same selection without relying on chance?

  **Answer:** The backend uses `random.SystemRandom().sample(PROFILES, total_pitches)`, so a session samples without replacement from all 19 entries. There is no API seed or explicit queue option. The saved `pitch_queue` preserves a selected session's case order, and each active pitch is copied from its catalog entry. Reconstructing a fresh selection from a seed is unsupported; the offline review instead used an explicitly seeded in-memory session harness.

- SET-06: Do session length, starting capital, or scenario order make some players unable to fund an otherwise suitable borrower, and how is that reflected in evaluation?

  **Answer:** Difficulty gives each player seat its own starting balance of $350,000, $250,000, or $175,000; it does not change the profile or AI caps. Accepted principal is deducted only from the winning player's balance and no repayments arrive during play. P19 requires a minimum $175,500 bid, already beyond Hard starting capital. Earlier funding can further restrict later opportunities. Decision Fit has no opportunity adjustment, while the profit contribution divides by starting capital, so equal skill is not normalized across sessions or difficulties.

## 4. CRS source and runtime boundaries

Context: [README technologies](../README.md#technologies-used) and [profile provenance](scorecard-logic.md#founder-profiles-what-is-fictional-and-where-it-comes-from). Sources: runtime imports/configuration in [the API](../backend/app/main.py), [dialogue module](../backend/app/agents.py), [portfolio agent](../backend/app/portfolio_agent.py), and [catalog](../backend/app/catalog.py).

- CRS-01: How is the documented boundary between CRS MCP development tooling and runtime gameplay maintained, and how could a judge verify which actors actually make CRS requests?

  **Answer:** The inspected runtime calls Grok and SpacetimeDB, using bundled catalog cases for applicant facts. There is no running MCP client, CRS report endpoint, or CRS credential configuration in those paths. The attached CRS MCP server is an assistant/development source of guides, schemas, and fixtures; it is not an additional runtime game-state database or an agent tool invoked during a turn. The spec's optional report pull is historical.

- CRS-03: What source artifacts establish the provenance of bundled credit facts if gameplay does not make a live CRS request?

  **Answer:** The repository evidence is the catalog's persona IDs, credit values, and authored facts. It does not retain raw bureau responses, request IDs, exact acquisition dates, model-name metadata, or a field-by-field import log. `sandbox_expected_score` is another stored catalog value rather than an independent runtime check. The source relationship can be described as bundled CRS-inspired synthetic cases; a stronger report-level provenance claim is not established by these files.

- CRS-05: How is a consumer credit report distinguished from evidence about the borrowing business and its ability to service debt?

  **Answer:** The credit evidence is personal consumer-credit evidence associated with a synthetic owner. The business's other four Cs come from separate fictional scalars, not verified business financial statements, business-credit reports, or an executed guarantee. `assess` combines them in the teaching rubric. The runtime does not call criminal or eviction products or include those screening categories as financial model fields.

- CRS-07: When bureaus disagree, what rule chooses the operative evidence, and what review is required before relying on it?

  **Answer:** There is no runtime bureau merge or reconciliation algorithm. P17's sentence describes 760 from TransUnion, no Equifax file, and 700 plus a charge-off from Experian, while its operative profile stores one `credit_score` of 760 and a derogatory count of 1. `assess` uses those stored scalars. P15 similarly uses a stored 740 despite its frozen-bureau narrative. The prose raises review issues; the engine does not resolve them before lending.

## 5. Grok characters and conversation context

Context: [dialogue and turn flow](../README.md#dialogue-and-turn-flow). Sources: `_player_exchange_spec`, `_turn_sharks`, `_recent_dialogue`, and `table_exchange` in [agents.py](../backend/app/agents.py), plus investor settings in [the catalog](../backend/app/catalog.py).

- AI-02: Are the sharks independent model agents, characters produced within one request, or a hybrid, and what evidence supports the chosen description?

  **Answer:** The founder and investors are characters generated within one structured Grok response per exchange. A player question requests four strings: founder answer, investor question, founder follow-up, and investor reaction. Pass/exit exchanges request three strings. A nonmatching offer requests those three plus a direct founder reply, played immediately after the player offer. Complete table exchanges can be regenerated twice when validation fails. Other pending offers can add a separate founder-response request; the newly submitted bid is excluded from that pass because it was already answered. Replies use the player seat name; legacy sessions use Guest shrimp. Grok receives an acknowledgment/counter mode based on requested funding, rate, and royalty, but the backend owns deal eligibility and final selection. These voices are generated conversation, not independent analytical corroboration. A matching new human bid is the exception: full requested funding, a rate at or below the opening rate, and no royalty produce an immediate system-authored acceptance with no Grok call. The existing input and available-capital checks still apply, but the hidden risk benchmark does not veto a borrower accepting those terms.

- AI-03: What information does each generated speaker receive: public pitch facts, disclosed facts, the full private profile, prior offers, hidden grades, or benchmark decisions?

  **Answer:** A question request contains public business context, the player question, all five supplied disclosure facts, two investor profiles, and recent dialogue. The keyword-selected fact is a hint for the player answer; the investor follow-up still has its own assigned fact. Numeric validation allows only numbers in supplied disclosures/public pitch details for the player answer and only its assigned fact for the follow-up. It does not send the full numeric profile, calculated grade, or benchmark. Offer/pass/exit exchanges retain one assigned fact for the investor question. An offer also supplies proposed amount, rate, royalty, term, security, player name, requested funding/rate, and an acknowledgment/counter mode. The separate founder-response request now also receives each submitted bid so it can distinguish matching funding/pricing from bids requiring a counter. Spoken responses may use requested counter terms but cannot invent numbers, restate numeric bid terms, or announce a final deal. Naturalness and semantic truth are not established by these numeric/length checks.

- AI-05: Which instructions define each shark's personality, and how do they affect tone, topic selection, advice, and actual offers respectively?

  **Answer:** The catalog configures Kevin as blunt and terms-focused, Lori as encouraging and product/customer-focused, and Mark as direct and operations-focused. `_shark_context` passes those broad traits into the common prompt. Follow-up topics and speakers cycle by round: Kevin/conditions, Lori/capacity, then Mark/collateral, and round 4 returns to Kevin/conditions, with the next investor reacting. Opening bidder selection, capital limits, grade appetite, and the first bid's price are separate fixed Python rules rather than model decisions. After a founder counter, that shark's catalog `counter_response` can keep the bid or trim it once. Grok does not choose the revised rate or royalty. The spoken reply is the catalog sentence for the Python choice.

- AI-06: Does a shark's language about concern or enthusiasm correspond to its subsequent offer behavior, and how are contradictions detected?

  **Answer:** The generated reaction is not consumed by offer generation. A skeptical line can be followed by an eligible deterministic offer, or an enthusiastic line by no offer, because `_shark_offer_for` uses round, pending bids, grade appetite, and capital. The inspected validators do not compare sentiment with the later financial action. A later counter reply can change a pending shark bid once, and that change comes from the catalog counter policy, not from reading the reaction. Distinct voices describe a simulated table; their prose is not the authority for lending intent.

- AI-08: How much conversation history is retained, and what evidence shows that truncation does not remove qualifications or earlier corrections?

  **Answer:** `_recent_dialogue` examines the last twelve messages, removes stage-manager round events, and retains at most eight spoken entries. It now includes human questions, offers, founder counters, and investor replies so the founder can respond to recent negotiation context. This remains a bounded window and can drop older qualifications or corrections; persistence of the full transcript does not mean the full history is supplied to Grok.

## 6. Question routing and available evidence

Context: [question routing](../README.md#question-routing-and-investor-behavior) and [public response boundaries](data-model.md#public-response-and-reveal-boundaries). Sources: `classify_question`/`fact_for`, `_append_question_exchange`, `_public_state`, and [UI rendering](../frontend/src/main.ts).

- INFO-01: How is a free-text question mapped to an underwriting topic, and how is that mapping evaluated against human judgments?

  **Answer:** `classify_question` case-folds the text and counts whether each configured keyword appears as a substring. It selects the maximum `(match_count, topic)` tuple; ties follow topic-name ordering. No match returns `None`. This still chooses the coverage label and offline response, but live Grok now receives all five disclosure facts and public pitch context, with the selected fact only as a hint. It can answer a mixed-topic or differently worded question from those supplied facts. This is prompted semantic selection, not a separately evaluated question-understanding model; coverage chips still use the keyword/topic tracker.

- INFO-04: Does "What you've covered" indicate a topic was mentioned, that the player understood it, or that enough evidence exists to underwrite it?

  **Answer:** `disclosures` records the routed topic and the assigned investor follow-up topic after a completed exchange; pass/exit also record their assigned topic. The UI renders those labels as covered. It does not check the player's understanding, document sufficiency, or whether every qualification was displayed. `score_session` does not read this list, so coverage is a conversation tracker rather than an underwriting-completion or scoring requirement.

- INFO-05: What critical facts can a diligent player discover within the question and round limits, and which remain unavailable before a decision?

  **Answer:** There is one player question per round. Investor follow-up topics cycle through conditions, capacity, and collateral as rounds continue. Questions are optional before offer, pass, or out. A pitch ends after three rounds when no offer has been made. Once an offer exists, one more round is played, and the pitch ends if that round has no new offer, so active bidding can run longer while new offers keep arriving. A nonmatching submitted offer gets a named direct founder reply before investor discussion; other pending offers get named responses when the round settles. Generated responses to other pending offers can acknowledge matching funding/pricing or counter different terms; these generated lines cannot decide a deal. A new matching human bid uses the immediate system-acceptance path. Each countered shark answers. The answer can trim that shark's bid once, or leave it unchanged. At that close the founder accepts the best qualifying offer or walks away. The conversation badge shows the current round number only. It does not display a maximum or a quiet-round fraction. A submitted offer is added under the active seat's name; the active player's client renders its speech bubble. The round count is therefore not a guaranteed chance to investigate all five Cs. The backend grades the complete hidden profile whether or not its facts were discovered. An active player matching the displayed request bypasses further rounds and dialogue generation, and that bid is accepted immediately; the transcript remains visible in an explicitly accepted review screen.

- INFO-09: Can archetype names, public API fields, competitor prices, or premature balance changes reveal hidden grades or outcomes before the intended disclosure?

  **Answer:** Public pitch responses include stable IDs, founder/company names, and archetypes such as `THE TRAP` or `THE UNICORN`, which can reveal case identity or suggest risk. In `pitch_review`, accepted offers and a changed human balance can disclose the winner while `result` is withheld. After reveal, result JSON contains the grade even though the intermediate result screen omits it. The implementation does not provide strict information concealment until the final scorecard.

## 7. The five Cs: Character

Context: [five Cs formulas and limits](scorecard-logic.md#five-cs-assessment-and-benchmark). Source: the actual branches in `assess` in [underwriting.py](../backend/app/underwriting.py), compared with the [catalog fields and disclosure sentences](../backend/app/catalog.py).

- CHAR-01: How is Character defined without equating financial hardship or a credit score with a person's moral worth?

  **Answer:** Character is a numeric game component derived from personal credit score, derogatory count, and two flags. With a score, `assess` scales `(score − 300) / 5.5`, subtracts four points per derogatory signal, then applies thin-file and severe-delinquency penalties. A missing score uses 50. No management-experience, promise-keeping, or moral-character assessment is implemented; the label should be read as the game's credit-history component.

- CHAR-04: How are the severity, age, frequency, payment status, and subsequent recovery of derogatory events distinguished?

  **Answer:** The profile has a count and a coarse `severe_delinquency` flag. Event dates, disposition, paid status, bankruptcy-plan performance, and recovery trends occur in authored sentences rather than structured event inputs. They receive no separate time decay or event-specific calculation. Two equally counted events can therefore have the same numerical effect despite materially different narrative histories.

- CHAR-06: How are thin, missing, frozen, stale, and disputed files handled without presenting unknown creditworthiness as either proven strength or proven weakness?

  **Answer:** Missing scores become neutral Character 50, and the thin-file/severe penalties are only applied in the branch with an available score. The engine otherwise sees a single scalar score plus flags, not separate frozen/disputed/identity states. P04, P12, and P20 all lack a score; P15 stores an alternative-bureau 740. Recommendations to verify or review remain prose, with no mandatory manual-review or identity-clearance gate.

## 8. The five Cs: Capacity

Context: [five Cs formulas and limits](scorecard-logic.md#five-cs-assessment-and-benchmark). Sources: `assess`, `benchmark`, and [the decision handler](../backend/app/main.py), which passes the original request amount into the assessment.

- CAP-02: What exactly does "monthly free cash flow" include and exclude: taxes, owner draws, maintenance investment, working-capital changes, and existing debt service?

  **Answer:** `monthly_free_cash_flow` is a fixed catalog number. The fact strings generally describe cash remaining after operating costs, while existing monthly debt is a separate field deducted through the DSCR denominator. The code does not define or reconcile taxes, owner distributions, maintenance investment, working-capital changes, or financial-statement periods. It also does not remove one-time revenue identified in a sentence, so its accounting meaning is only as precise as the authored case.

- CAP-04: What is the debt-service coverage ratio formula, and are its numerator and denominator defined on consistent accounting and time bases?

  **Answer:** The actual formula is `monthly_free_cash_flow / max(1, ask_amount × 0.034 + monthly_existing_debt)`. Capacity is that ratio divided by 2.4, multiplied by 100, clamped, then rounded. The assessment returns DSCR rounded to two decimals, and the benchmark uses that rounded value. Numerator and debt-payment inputs are named monthly, but there is no statement reconciliation establishing consistent accounting definitions.

- CAP-05: Does the debt-service denominator include the actual proposed principal, interest rate, amortization schedule, term, fees, royalties, and existing obligations?

  **Answer:** Only the original ask's fixed 3.4% payment estimate and existing monthly debt enter the denominator. The proposed amount, selected rate, term, royalty, security, fees, and amortization schedule are not used. A changed offer does not trigger a different capacity assessment because the decision route always calls `assess(profile, pitch.ask_amount)`. Payment adequacy for the actual contract is therefore not established by the displayed DSCR.

- CAP-12: Under what circumstances does inadequate capacity require rejection, deferral, or restructuring even when the other Cs look strong?

  **Answer:** There is no standalone minimum-DSCR gate, defer action, or required restructuring workflow. Capacity contributes 25% of the weighted grade, so stronger components can offset it. Offers are barred by the final grade/target-rate rules and, at grade 4, require the security flag. Those are aggregate game rules, not a direct proof of repayment capacity.

## 9. The five Cs: Capital

Context: [five Cs formulas and limits](scorecard-logic.md#five-cs-assessment-and-benchmark). Sources: the Capital expression in [assess](../backend/app/underwriting.py) and authored equity/reserve facts in [the catalog](../backend/app/catalog.py).

- EQUITY-01: Does owner equity mean contributed cash, retained earnings, accounting net worth, or funds still available for the proposed project?

  **Answer:** `owner_equity` is an authored dollar scalar described variously as invested or committed owner funds. The Capital score divides it by the original ask and scales against 0.6. There is no reconciliation to a balance sheet or distinction among contributed cash, retained earnings, liquid reserves, and funds already spent. Extra reserves mentioned in dialogue are not separate model inputs.

- EQUITY-06: Could a founder receive strong capital credit for money already spent while lacking the cash needed to survive a shortfall?

  **Answer:** Yes. The Capital calculation credits the stored equity amount without checking cash availability after closing. Narrative references to a small reserve or cash tied up in assets do not reduce that component automatically. The game has no separate post-closing liquidity test, so invested value can generate a strong Capital score without demonstrating an available cash buffer.

## 10. The five Cs: Collateral

Context: [five Cs limits](scorecard-logic.md#what-the-five-cs-calculation-does-not-evaluate) and [offer eligibility](scorecard-logic.md#offer-eligibility-and-founder-selection). Sources: `assess`, `benchmark`, `score_session`, and `_deal_candidate`.

- COLL-01: Is the collateral value a purchase price, book value, market estimate, or recoverable liquidation value, and who established it?

  **Answer:** The catalog supplies a dollar estimate and a sentence, often describing resale or support value. The model uses the scalar rather than deriving it from individual assets. No appraisal source, valuation date, sale-cost schedule, or independent reviewer is stored. It is a fictional collateral assumption, not a demonstrated recoverable amount.

- COLL-04: Does marking an offer "secured" require sufficient eligible assets, or can it imply protection that the scenario has not established?

  **Answer:** A human submits a boolean `secured`; the API does not require an asset selection, lien position, or proof that collateral covers the loan. Grade 4 eligibility checks that flag, while AI offers are marked secured at grade 3 or worse. Thus the flag can satisfy an eligibility rule without verifying the protection its label suggests.

- COLL-05: How does security affect expected recovery, pricing, and approval independently of the borrower's ability to make payments?

  **Answer:** The collateral scalar influences the borrower's weighted grade and the suggested benchmark amount. The offer's security flag separately gates grade 4 eligibility. It does not reduce the scorecard's grade-based loss fraction, change the founder preference, or produce a recovery calculation. Two otherwise identical secured and unsecured eligible offers therefore have the same expected game-profit formula.

## 11. The five Cs: Conditions

Context: [five Cs limits](scorecard-logic.md#what-the-five-cs-calculation-does-not-evaluate). Sources: the `market_strength` expression in [assess](../backend/app/underwriting.py) and [catalog narratives](../backend/app/catalog.py).

- COND-01: What measurable evidence supports the conditions assessment, and which parts are an author's subjective judgment?

  **Answer:** Conditions is `market_strength`, a fixed 0–100 catalog scalar clamped by `assess`. The associated sentence explains concentration, contracts, seasonality, or demand, but no market feed, dated industry dataset, or numerical derivation is connected to it. The source establishes an authored teaching judgment, not a measured economic forecast.

- COND-06: How are adverse conditions translated into a financial stress or lending restriction instead of remaining a narrative warning with no effect?

  **Answer:** Changing `market_strength` changes the weighted result; adding or changing a cautionary sentence alone does not. There is no revenue stress, delayed-receivables simulation, seasonal liquidity model, or contract-expiry event that recalculates cash flow. The narrative may help the player interpret a scenario, but the engine does not automatically translate it into an additional restriction.

## 12. Risk grades and the benchmark

Context: [assessment/benchmark formulas](scorecard-logic.md#five-cs-assessment-and-benchmark) and [current inventory](scorecard-logic.md#current-scenario-inventory). Sources: [underwriting.py](../backend/app/underwriting.py), `_deal_candidate`, and request/decision validation in [main.py](../backend/app/main.py).

- RUBRIC-01: What evidence justifies the component formulas, scaling, caps, floors, and rounding documented in the scorecard guide, and how sensitive are results to those choices?

  **Answer:** The component scales, weights, rounding, grade cutoffs, and target rates are constants in `underwriting.py`; the scorecard guide records the exact calculations. The repository contains no fitted model, calibration dataset, or derivation establishing those choices. Rounding happens before grade assignment, so nearby scores can cross a threshold and change the target rate. The current inventory demonstrates the resulting categories, not empirical lending accuracy.

- RUBRIC-04: Can strength in one component offset a fatal weakness in another, and which conditions require a non-compensating gate or manual review?

  **Answer:** Yes: the total is a weighted sum, so strong components can offset weak ones. The hard gates are the resulting grade's target-rate availability, the bid floor, and grade 4 security, alongside API bounds and the acting seat's capital. There is no independent identity, documentation, minimum-DSCR, or manual-review gate. The offline check accepted P12's eligible offer despite its verification-hold narrative.

- RUBRIC-08: How are the documented benchmark amount and rate rules reconciled with permitted funding amounts and the player's security and term choices, and what happens if they conflict?

  **Answer:** The benchmark shrinks the ask using capacity and collateral fractions, floors to $1,000, and applies a $25,000 minimum. The API instead requires a bid of at least 78% of the ask and enough capital in the acting player's seat. Four current suggested principals—P03, P07, P11, and P13—fall below that bid floor. The benchmark does not supply term or security, and Decision Fit does not compare principal against it. These rules are not fully reconciled.

- RUBRIC-09: Is the benchmark independent of the system being judged, and how would its own errors be discovered instead of rewarded as correct answers?

  **Answer:** The benchmark uses the same assessment and grade-rate table as the game. It is not an independent underwriter, optimization engine, or external validation service. There is no implemented Coinbase/x402 coach. Agreement establishes consistency with the local comparison rule; it does not establish that the rule is financially correct. The unusable benchmark amounts are a concrete example of why benchmark output and game validity must be distinguished.

## 13. Offers and founder selection

Context: [offer eligibility and founder selection](scorecard-logic.md#offer-eligibility-and-founder-selection). Sources: `_shark_offer_for`, `_founder_preference`, `_settle_round`, `_choose_winner`, `_complete_ai_negotiation`, and `submit_decision` in [main.py](../backend/app/main.py).

- DEAL-01: Which terms are economically operative—amount, interest, term, royalties, collateral, covenants, guarantees—and which are only displayed choices?

  **Answer:** Principal, annual-rate input, royalty/revenue share, term, and a security flag are stored. Principal affects bid limits, balance, founder funding preference, and illustrative P&L. Rate affects eligibility, founder preference, Decision Fit, and P&L. Royalty reduces founder preference but contributes no P&L. Term affects P&L but not DSCR or founder preference. Security gates grade 4 but does not verify assets or change loss severity. Equity, covenants, guarantees, and revolving draw accounting are not implemented.

- DEAL-07: How do the sharks' capital constraints, risk appetites, and pricing rules operate across pitches, and are they comparable to the player's constraints?

  **Answer:** AI investors use the complete hidden grade, fixed capital caps, grade appetite, and fixed rate premiums. Bids start in round 2. Kevin has $185,000/grade ≤3, Lori $145,000/grade ≤4, and Mark $230,000/grade ≤3. Their caps reset in effect each pitch; only the winning player's capital is depleted across the session. First/last eligible investor selection depends on the round and pending offers, not Grok's generated attitude. The opening price is the grade target plus that investor's fixed premium. A founder counter can then make the same shark replace the pending bid once, using the catalog gap and cut for that personality, without going below the grade target. These constraints are intentionally different game mechanics, not equal investor balance sheets.

- DEAL-08: Does the founder choose on funding sufficiency, total financing cost, repayment feasibility, security burden, timing, or a different objective?

  **Answer:** When the quiet-offer rule closes the pitch, the backend first filters pending offers by grade target rate, minimum funding, and grade 4 security. If any qualify, it maximizes `100 × min(1, amount/ask) − 2.1 × max(0, rate−opening_rate) − 1.5 × royalty` over that set and accepts one. If none qualify, it rejects the pending offers and the founder walks away. Term, amortized payments, asset verification, and a minimum preference score are absent. Ties follow list order. Nonmatching bids wait for this quiet-table rule. A matching new player offer closes immediately instead. The rule selects a game offer rather than verifying borrower affordability. Before that path, a newly submitted human offer matching the full requested funding, no higher rate, and zero royalty is accepted immediately. This route does not filter by the hidden grade or required benchmark rate/security. Term and security are not requested profile fields and do not gate the match. The immediate bid takes the deal, competing pending bids are rejected, and only its seat is charged. The scorecard can therefore penalize a funded grade 4 or grade 5 loan.

- DEAL-12: What exactly distinguishes passing for one round, withdrawing a pending offer, and leaving the pitch, and which previously submitted offers remain legally active within the simulation after each action?

  **Answer:** Pass by the active seat generates another investor/founder/reaction exchange, founder counters for pending shark offers and all pending player-seat offers, and can advance the round or close it under the quiet-offer rule. Each countered shark replies. A reply that revises the bid withdraws the previous pending shark bid, appends the new one, and resets the quiet-offer clock. A hold does not. Pass does not withdraw any existing pending player offer and does not itself reset the quiet-offer clock. A replacement offer withdraws only that seat's previous pending bid. If the new bid meets the founder's displayed request it closes immediately; otherwise it resets the quiet-offer clock. A player offer is written under that seat's name, and the founder addresses the matching seat when countering it (legacy sessions use Guest shrimp). I'm Out marks only the active seat out and withdraws that seat's pending bids, and keeps the other investors in discussion until the same rule closes the pitch: three rounds if no offer has been made, or one round after the latest offer. That exit fast-forward also stops at round 24 if the quiet rule has not already closed the pitch. Ordinary offer and pass actions do not use that stop. An exit does not end the whole game. The visible offer list contains only pending/accepted records, while private state retains other statuses.

## 14. Scorecard, Decision Fit, and Underwriting Instinct

Context: [Scorecard Logic](scorecard-logic.md). Sources: `score_session` in [underwriting.py](../backend/app/underwriting.py), `_finish_pitch`, and [scorecard rendering](../frontend/src/main.ts). The offline examples below exercised the actual API handlers in memory mode.

- SCORE-01: What exact quantities do Decision Fit and Underwriting Instinct measure, and what evidence supports those names?

  **Answer:** Decision Fit is the rounded mean of heuristic per-pitch points, not a classification accuracy statistic. Underwriting Instinct is 80% of that mean plus 20% of a bounded illustrative-profit score. The five Cs weighted total is a separate borrower-assessment value. The names express teaching intent; the repository does not demonstrate that any of them measures a learner's independent underwriting ability.

- SCORE-02: What reproducible worked cases corroborate the documented metric formulas, including every per-pitch branch, constant, weight, clipping rule, rounding step, and aggregation?

  **Answer:** The scorecard guide records the exact branches, constants, rounding order, and formulas from `score_session`. Isolated offline checks reproduced a P08 $210,000/9%/36-month offer left in place until the quiet-offer rule accepted it: Decision Fit 100, P&L $48,300, profit score 69, and overall 94. Passing P05 with no offers produced Decision Fit 100 and overall 90. These examples verify those executed paths; they are not exhaustive branch tests or deployed-system validation.

- SCORE-07: How much do amount, term, security, royalties, and verification requirements matter relative to closeness to a benchmark interest rate?

  **Answer:** For a human win, direct Decision Fit deduction is `int(abs(rate−benchmark_rate) × 8)`, with a zero floor. It does not compare principal to the benchmark principal or reward term, security verification, royalties, or information gathered. Those fields can affect eligibility, founder selection, balance, or the separate P&L term. Grade-based losses are fixed fractions; amortization and royalties are omitted. A longer term can raise game profit without changing assessed repayment capacity.

- SCORE-09: Is question quality or evidence coverage scored, and if so how is genuine understanding distinguished from mentioning topic keywords?

  **Answer:** Question quality and evidence coverage are not scored. `score_session` uses completed case assessments, benchmark, winner, and that seat's retained offer; it does not consume transcript analysis, question count, or `disclosures`. A player can therefore receive high points through a correct guess or a blanket pass on a grade 5 case. The offline checks demonstrate scores of 94 and 90 respectively without player questions.

- SCORE-14: Are scores comparable across starting-capital settings, pitch counts, scenario difficulty, and order, and what prevents differences in opportunity from masquerading as skill?

  **Answer:** No cross-session skill normalization is implemented. Difficulty changes capital and feasible bids; order changes remaining capital; random case mix changes the available score branches. Pitches receive equal weight in Decision Fit, and profit is scaled by starting capital rather than by an independently standardized opportunity set. The final number describes that particular game under its rules, not a demonstrated comparison across difficulties or players.

## 15. Persistence and state ownership

Context: [SpacetimeDB Data Model](data-model.md) and [scorecard storage](scorecard-logic.md#where-the-profile-and-scorecard-are-stored). Sources: [session model](../backend/app/main_types.py), [store adapter](../backend/app/spacetime_store.py), [reducers](../spacetime/spacetimedb/src/index.ts), and API lifecycle.

- STATE-01: How is the documented division between FastAPI game state, SpacetimeDB persistence, and browser presentation enforced for borrower facts, messages, disclosures, offers, balances, pending outcomes, and final scores?

  **Answer:** FastAPI owns the authoritative game transitions and constructs the public response. With SpacetimeDB selected, the complete active session and completed case records are serialized into a private snapshot; the browser renders that state and maintains local playback controls. The reducer enforces typed arguments/version checks, not Python underwriting rules inside `stateJson`. Memory mode instead holds the session in one backend process. The data-model guide documents these boundaries.

- STATE-02: Which of those records survive a browser refresh, API restart, or deployment, and what distinguishes durable persistence from an in-memory fallback?

  **Answer:** SpacetimeDB snapshots are intended to restore the session after API restart, and the browser keeps a session ID to request it after refresh. Memory mode is lost on backend restart. Current-pitch messages restore with the snapshot; older transcript rows remain separately in the database but are not queried by the application. Initial entry animation and playback progress are browser state rather than persisted chronology. This review did not restart or probe the deployed database.

- STATE-03: Given the documented snapshot read path and separate transcript rows, what verifies that restored messages agree with the retained rows across writes, pitch transitions, and recovery?

  **Answer:** The adapter reads messages from `game_session.stateJson`, not from `conversation_message`. The write reducer atomically updates the snapshot and upserts the supplied current-pitch messages, but the app performs no independent read-time reconciliation between the copies. Advancing clears active messages; earlier rows remain stored without a transcript-history read endpoint. The table supports a possible ordered lookup, but the current app does not use it for replay.

- STATE-09: What retained record links a result to its profile version, rules version, prompts, model configuration, displayed transcript, and player actions?

  **Answer:** Saved state retains profile inputs, computed assessment/benchmark, offers, results, and scorecard; conversation rows include coarse source labels such as `xai` or `offline`. It does not record dedicated model, prompt, application-commit, or dependency-version metadata, original CRS report artifacts, or observed loan repayments. Offer statuses and messages can be updated rather than forming an immutable audit chain. A historical score can be displayed from its snapshot, but re-executing later code is not a guaranteed version-matched reconstruction.

## 16. Streaming, playback, and phase transitions

Context: [README turn flow](../README.md#dialogue-and-turn-flow) and [data-model operational limits](data-model.md#operational-limits). Sources: [API streaming/decision routes](../backend/app/main.py), [browser playback and navigation](../frontend/src/main.ts), and [stage entry](../frontend/src/studio.ts).

- LIVE-01: At each point in a turn, what is being streamed or displayed: model tokens, speaker progress, validated utterances, or timed playback of an already completed exchange?

  **Answer:** Grok tokens are streamed to FastAPI, and the question endpoint forwards speaker/progress and provisional field-delta events. The current browser displays progress labels during generation and ignores generated text deltas. After validation and saving, `complete` supplies the public session; the browser then stages the stored utterances in the transcript and 3D bubbles. Pass/out use a normal response and expose their generated exchanges together after processing, not incremental SSE conversation.

- LIVE-04: What determines that the conversation has actually been presented before decision controls become usable, including reduced-motion and background-tab behavior?

  **Answer:** The browser uses `speechActive` and `readingUntil` to disable turn controls while it reveals each incoming message over four seconds, separated by two-second gaps. A player-question sequence starts after an 850-ms pause. Reduced motion skips timed typing. Review's reveal control can call `showFullTranscript`, stop playback, and reveal the decision. These are UI rules; the API does not verify that the player read a message or completed playback.

- LIVE-06: If a stream disconnects, a save fails, or the player retries, how are duplicated questions, consumed turns, stranded controls, and inconsistent offers prevented?

  **Answer:** Question generation is validated before appending its canonical exchange, and the streamed route saves before emitting `complete`. There is no automatic reconnect, event-ID resume, or incoming-action idempotency key. A lost final event or save error can leave the browser unsure of the commit outcome; cancellation does not reverse a database transaction. Phase/question flags and version checks prevent some repeated transitions, but do not supply an end-to-end exactly-once guarantee or a tested recovery workflow.

- LIVE-07: How is the review, reveal, and scorecard lifecycle documented in both local guides verified across API and browser paths, including the noted scorecard endpoint/phase mismatch?

  **Answer:** The operative backend flow is `investigate → pitch_review → pitch_result`, then `/next` returns to investigation for another pitch. The final result carries a scorecard after reveal; the browser's final continue action fetches the regular session and renders it. No transition sets `complete`, so the separate scorecard endpoint remains inconsistent and returned 409 in the offline check. Review also exposes accepted offer/balance signals before result reveal. Both guides now describe these actual limits.

- LIVE-10: What event releases the game from the entrance cinematic into investigation, and can skipping, reduced motion, refresh, or a slow network consume dialogue or a round before the player can interact?

  **Answer:** `startGame` awaits stage readiness and the initial intro completion/skip callback before creating the backend session. Reduced-motion stage code calls completion immediately; if stage creation fails, the browser can proceed without the cinematic. Thus the initial UI flow does not consume a dialogue round during the walk-in. The API itself has no intro phase or completion proof, and subsequent `/next` handling loads the next pitch directly rather than replaying the full opening entrance.

## 17. Learning claims and readable interaction

Context: [README boundaries](../README.md#project-boundaries) and [scorecard examples](scorecard-logic.md#reproducible-offline-examples). Sources: score calculation, [HTML controls and announcements](../frontend/src/main.ts), [CSS](../frontend/src/style.css), and [speech/entry rendering](../frontend/src/studio.ts).

- LEARN-01: What evidence shows that a higher game score corresponds to better independent underwriting judgment rather than better negotiation or familiarity with the catalog?

  **Answer:** The repository demonstrates a working game rubric and explanatory scorecard, not a measured relationship between score and independent skill. No learner study or new-case assessment artifacts were found in the inspected files. The executed examples earn 94 by offering immediately and 90 by passing a grade 5 case without questions. A high score therefore cannot by itself establish the quality of investigation or real underwriting competence.

- LEARN-05: Can a player pause, revisit, or fully read a material disclosure without relying on a disappearing bubble, fast reading speed, or a particular browser zoom?

  **Answer:** The current-pitch transcript retains complete message text and scrolls. The bubble renderer keeps only its last four wrapped lines while text is typed, so it is not the full persistent record. Review can expose all current dialogue immediately, and reduced motion removes paced typing. There is no dedicated general pause control or earlier-pitch transcript viewer. Actual reading speed, viewport suitability, and accessibility compliance were not measured in this code review.

- LEARN-06: Can keyboard and screen-reader users obtain the same evidence and learn when dialogue finishes, an error occurs, or a decision becomes available?

  **Answer:** The UI uses native buttons/forms, labels, focus-visible styles, a skip-to-conversation link, status/live announcements, and a labeled capital progress bar. Reduced-motion handling applies to dialogue and entry. The 3D view uses pointer dragging; its text information is also represented in HTML. These are concrete accommodations in the code, not proof that keyboard, screen-reader, zoom, or contrast behavior meets every criterion. No browser or assistive-technology audit was performed.

## 18. Proposal and delivered scope

Context: [original proposal and its current-status comparison](../shark_tank_project_specs.md#current-implementation-compared-with-the-proposal). Sources: frontend/backend/module manifests and the runtime code referenced throughout this review.

- SPEC-01: Which requirements in the proposal were delivered, changed, deferred, or dropped, and what implementation reference or reproducible demonstration supports each status?

  **Answer:** The proposal's main delivered pieces are the procedural studio/entry, configurable sessions with a LAN shared-session preview, separate sequential investor seats, per-seat capital/scorecards, Grok dialogue, fixed underwriting/offer logic, review/scorecard UI, and snapshot/transcript persistence. Runtime CRS ingestion, normalized player/offer-ledger tables, direct client database subscriptions, equity/revolving accounting, and a Coinbase/x402 loan benchmark coach are absent from the inspected runtime. A separate investor-side paper portfolio feature now uses Coinbase's public candle endpoint and supplies qualitative context to the existing Grok call; it is not that proposed coach. The current-versus-proposal table in the spec records these distinctions; roadmap checkboxes are historical rather than completion evidence.

- SPEC-04: Which technology claims in the proposal—such as Tailwind CSS, the Grok Responses API, direct database subscriptions, and Coinbase/x402—are supported by the judged deployment rather than remaining design ideas or obsolete descriptions?

  **Answer:** The frontend manifest and source establish TypeScript, Vite, Three.js, and handwritten CSS; the backend uses FastAPI, Pydantic, HTTPX, and streaming Chat Completions. SpacetimeDB is accessed through the Python adapter. The portfolio agent also reads public Coinbase Advanced Trade candle data directly for three fictional investor portfolios and passes qualitative summaries into the existing Grok request. This does not use Coinbase for Agents MCP, Coinbase Wallet MCP, or x402, and does not send orders. Tailwind, the Responses API, and browser SpacetimeDB subscriptions are not runtime integrations in the inspected code. A deployed environment could differ, but its served revisions and service configuration were not independently inspected here.

## Review record

The initial documentation pass retained 73 of the existing 197 questions and pruned 124 without creating replacements. All retained questions have inline answers; no questions were added in the later portfolio update. That update revised the existing Coinbase technology answers and aligned the README, data-model guide, scorecard guide, and proposal comparison with the portfolio code.

Local diagnostics enumerated the 19 catalog entries, calculated their grades and benchmarks, and checked deep-copy isolation. In-process FastAPI checks used memory storage and an empty Grok key to exercise an immediate offer, all-pass resolution, an invalid benchmark amount, the identity-mismatch case, streamed-question completion, pass-after-question behavior, and the final scorecard endpoint mismatch. Those checks passed without Grok or SpacetimeDB requests. They do not establish production performance, empirical loan accuracy, or learner outcomes.
