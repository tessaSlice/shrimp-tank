# Shrimp Tank

Shrimp Tank is a fictional, single-player B2B loan negotiation game. The player sits in the middle investor position, questions a founder, reviews the other investors' discussion, and decides whether to offer a loan, pass, or leave the pitch. A five Cs rubric explains the rules-based outcome. The game is educational and does not make real credit decisions.

The project has three parts:

- A Vite, TypeScript, and Three.js browser game with a procedural low-poly shrimp studio.
- A FastAPI service that owns session rules, Grok dialogue, and underwriting.
- A SpacetimeDB TypeScript module that stores session snapshots and ordered conversation messages.

The current game is single-player. The conversation table and persisted session model are groundwork for multiplayer; authenticated rooms, shared client subscriptions, and membership checks are not implemented yet. The score reflects a fixed teaching rubric, not demonstrated underwriting skill or a calibrated repayment prediction.

## What the game does

- Starts with a skippable presenter entrance: backstage doors, a widened hallway, outward-opening wooden stage doors, and a final investor-seat camera shot. A reduced-motion preference skips the animation.
- Places the player at the center of a semicircle of investor shrimps. The studio, floor, windows, stage lighting, and low-poly characters are generated in Three.js; no external shrimp model is required.
- Lets a player choose one to four pitches and a starting-capital difficulty.
- Grounds fictional founder scenarios in synthetic CRS persona facts and locally authored business profiles. The game does not pull credit reports at runtime.
- Uses one Grok request to produce a structured, fact-constrained turn for the founder and two investors. It does not make one model call per investor.
- Keeps underwriting and deal selection deterministic in the backend; Grok supplies dialogue, not credit decisions.
- Preserves the whole conversation through the offer decision, then asks the player to reveal the founder's selection before moving on.
- Includes a debug reset control that deletes the active session and returns to setup, plus live status announcements and reduced-motion support.

## Technologies Used

### xAI Grok API

Grok gives the investors distinct, configured personalities. Kevin O'Leary's game profile focuses on return, pricing, and downside protection; Lori Greiner's on product clarity, customer demand, and execution; Mark Cuban's on operating leverage, customer concentration, and scale. These are fictionalized game personas, not replicas or endorsements.

The backend sends one structured request per player question. That request produces the founder's answers and a short exchange between two investors, using the selected sharks' profile instructions. Investor lines are checked for length and numbers; the question line must end with a question mark. This keeps the voices distinct while avoiding a separate request and extra latency for every shark. Grok does not decide creditworthiness or whether a deal is accepted; deterministic Python rules handle those outcomes. The API key stays on the backend.

Detailed personality prompts live in `SHARKS[].ai_profile.system_prompt` in `backend/app/catalog.py`. `backend/app/agents.py` combines the two selected personalities with shared instructions in the actual system message for question and pass/exit exchanges. Kevin emphasizes repayment and downside, Lori customer demand and fulfillment, and Mark execution and operating bottlenecks. The [personality guide](docs/shark-personalities.md) links the public research, explains the design interpretation, and describes the retained short-line rules and offline request checks.

**Challenges encountered:** Separate calls for each shark made the first question feel slow and made the table seem to be waiting on several independent agents. The implementation now asks Grok once for the complete four-line exchange. Another mismatch was that the browser showed “responding” status labels while the conversation text did not appear until later. The client now re-renders the saved exchange as soon as the stream completes and plays it in sync with the speech bubbles. During Grok generation, it still shows progress labels rather than partial dialogue; timed playback starts after the full response is validated and saved.

### SpacetimeDB

SpacetimeDB stores durable session snapshots and an indexed copy of the conversation. The `game_session` row holds the complete serialized game state; `conversation_message` holds one ordered row per message. Both are written in the same reducer transaction. The tables are private because the session snapshot contains hidden borrower profiles. A private `session_cleanup_schedule` table runs database-side cleanup every 20 minutes: sessions whose last saved update is more than two hours old are deleted together with all their conversation rows. The current FastAPI adapter restores the transcript from the session snapshot; it writes the message rows but does not query them. The browser receives dialogue over FastAPI server-sent events and does not connect to SpacetimeDB directly, so multiplayer rooms and live database subscriptions remain future work.

The field definitions, payload shape, indexes, reducer behavior, privacy choices, and rationale for each table are documented in [SpacetimeDB Data Model](docs/data-model.md).

Session expiration is based on the last successful save, not the game's creation time. Questions, passes, offers, reveals, and pitch advancement renew it; reads, camera movement, and leaving a page open do not. Both unfinished and completed games expire under this policy. The next scheduled sweep normally removes an idle game between two hours and two hours twenty minutes after its last save. Reset requests immediate deletion, while Exit, Back to Lobby, and Run It Back leave previous records for expiration. See [cleanup behavior and testing](docs/data-model.md#session-expiration-and-cleanup).

The founder-profile data path, five Cs rubric, benchmark, Decision Fit, and Underwriting Instinct formulas are documented in [Scorecard Logic](docs/scorecard-logic.md).

For a focused, code-backed review of data origins, architecture, the five Cs, scoring, and gameplay, see [Methodology Questions and Answers](docs/methodology.md). Its retained questions are answered in place and distinguish inspected implementation, isolated offline checks, and evidence the repository does not establish. Detailed formulas and the current case inventory live in the scorecard guide.

**Challenges encountered:** Local FastAPI startup requires a SpacetimeDB token, supplied by `spacetime login` or `SPACETIMEDB_TOKEN`. The backend does not ping the database during startup, so a missing or unpublished database appears later as a failed persistence request. Deployed FastAPI needs the owner token as a server secret. The tables are private because the session row contains hidden profiles and unrevealed outcomes. A separate conversation table provides an indexed path for future transcript queries; the current adapter restores the transcript from the session snapshot and does not read the message rows. This is persistence groundwork, not multiplayer synchronization: FastAPI remains the state owner and the browser does not subscribe to SpacetimeDB yet.

### CRS CalHacks MCP server and CRS sandbox

The npm package [`@crscreditapi/crs-calhacks-mcp-server`](https://www.npmjs.com/package/@crscreditapi/crs-calhacks-mcp-server) is used during development as a reference and discovery tool. We use tools such as `get_personas` and `get_product_guide` to inspect synthetic applicants and product details; `get_api_schema` and `get_test_data` help check product fields and canned cases. That information informed the local synthetic persona catalog.

The deployed game does **not** call the MCP server or CRS APIs at runtime. MCP is the developer/agent interface; the FastAPI app has no MCP client dependency. CRS persona information was used to construct the bundled fictional founder profiles, so gameplay does not require CRS credentials and does not make credit-report requests.

CRS is the external credit-data source, exposed through product APIs and MCP resources; this does not establish access to CRS's internal database tables or identify its database engine. SpacetimeDB separately stores the game's sessions and conversation records.

The profile path is:

1. MCP persona information provides synthetic examples that inform the founder credit profiles.
2. `backend/app/catalog.py` associates 19 playable persona IDs and synthetic founder identities with authored businesses, requests, revenue, repayment capacity, owner equity, collateral, and market conditions. P14 is not a playable case. These are fixed entries, not new financial profiles generated each time a presenter appears.
3. Bundled credit facts and business metrics provide the evidence used by Grok dialogue and the deterministic underwriting model. The data-model guide lists [field origins and CRS-backed facts for every persona](docs/data-model.md#founder-field-origins). By project convention, borrower/scenario inputs without a directly available CRS source are labeled **AI synthesized**, including fixed financial inputs and local credit proxies. The guide traces those inputs into the risk score; this classification does not mean Grok generates the profile during gameplay.

CRS supplies synthetic persona examples for the bundled catalog; the fictional business and five Cs teaching profile are curated locally. In `backend/app/catalog.py`, `PROFILES` starts empty and all 19 playable cases pass through `_crs_presenter`; a session randomly selects 1–4 cases from that full list without replacement. P14, the deceased-file case, is excluded. Original report bodies, request IDs, bureau-model metadata, and a field-level import history are not retained in the repository, so the bundled values are not independently reconciled to source reports at runtime. No real applicant data is used.

**Challenges encountered:** The MCP guide covers several CRS products, and the initial design added an optional direct sandbox-report pull during a pitch. That feature required credentials and could update the credit score mid-game, adding a second source of state for the underwriting decision. To keep the game simpler, the report panel, runtime connector, endpoint, and credential settings have been removed. CRS persona examples remain bundled as synthetic scenario facts; Grok phrases those supplied facts conversationally, and the backend rejects founder answers with numbers absent from the selected fact. That check does not prove every non-numeric claim is supported, so the prompt remains an important safeguard.

### TypeScript, Vite, and Three.js

TypeScript and Vite build the browser client; Three.js creates the shrimp actors and studio from code-generated geometry, materials, and lights.

**Challenges encountered:** The stage has appeared as a mostly empty color panel during layout changes, and some camera/UI arrangements obscured the environment or the speech bubbles. The current camera supports limited dragging and speaker-following rather than a permanently locked view. Door frames briefly looked like bars across the presenter's route; a thin cyan horizon line in the city-window texture can still be mistaken for one. An external shrimp model was tried and then reverted, so the characters remain procedural. Long dialogue also obscured the set: the transcript keeps the full current-pitch text, while each 3D bubble shows the last four wrapped lines as text arrives. On desktop, the scrolling conversation is in the right rail, the summary panels are on the left, and the decision dock stays below. Reduced-motion, focus styles, labels, and live announcements exist; no completed accessibility audit is claimed.

### Python, FastAPI, Pydantic, HTTPX, and Render

FastAPI owns session transitions and underwriting. HTTPX calls Grok from the server; the SpacetimeDB adapter persists game state. Render hosts the API and static frontend; `scripts/deploy-render.sh` publishes the SpacetimeDB module and triggers the existing Render services.

FastAPI uses Pydantic for input validation. The request models in [`backend/app/main.py`](backend/app/main.py) define accepted fields, types, defaults, and limits for starting sessions, asking questions, and submitting decisions. Examples include 1–4 pitches per session, questions between 2 and 400 characters, and loan terms between 6 and 84 months. Invalid inputs receive an HTTP 422 validation response. The models allow Pydantic's default type conversions and ignore unknown fields; they are not configured for strict typing. Amount and rate are optional in the request model and required separately by the offer handler. Backend handlers also enforce phase, balance, and offer-eligibility rules. Passing these checks does not establish that a real loan is sound.

The SpacetimeDB adapter currently makes synchronous HTTPX calls directly from async routes. Those database requests can block a worker's event loop and delay other requests or dialogue streams. Session locks are local to one process; the database's version check rejects stale saves across processes but does not serialize the preceding Grok generation. See [SpacetimeDB operational limits](docs/data-model.md#operational-limits).

**Challenges encountered:** The root `.env` is intentionally ignored and is not present in a fresh clone, while Uvicorn resolves `--env-file` paths from the current directory. That caused the missing `../.env` startup error when setup was incomplete or run from the wrong folder. “Can't reach the game server” also occurred when Vite was running on port 5173 but FastAPI was not running on port 8000. Render also needs an exact `FRONTEND_ORIGINS` CORS value and `VITE_API_BASE` at frontend build time. A game-state bug made **I'm Out** end the session; the backend now records the player as out while allowing the other investors to finish the pitch and the player to review its result. The setup instructions below configure both processes, credentials, and the SpacetimeDB connection.

## Run locally

Requirements: Python 3.11+, Node.js 20.19+ or 22.12+, npm, the [SpacetimeDB CLI](https://spacetimedb.com/docs/), and an xAI API key for live Grok dialogue. The app defaults to persistent SpacetimeDB state. Live Grok is required for personality-based dialogue; without the key, the app falls back to its scripted offline mode.

1. Create a virtual environment and install the API dependencies:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r backend/requirements.txt
   ```

2. Create the ignored root environment file from the template if you do not already have one:

   ```bash
   cp .env.example .env
   ```

   Edit `.env` and set at least:

   ```dotenv
   GROK_API_KEY=your-xai-api-key
   SESSION_STORE=spacetime
   SPACETIMEDB_URI=https://maincloud.spacetimedb.com
   SPACETIMEDB_DATABASE=credit-tank-state
   SPACETIMEDB_TOKEN=
   ```

   `GROK_API_KEY` is required for live shark personalities. Keep it in the ignored root `.env`; never put it in a frontend `VITE_*` variable. For local SpacetimeDB use, the token can stay blank because the backend reads the CLI login token. CRS credentials are not required; the game uses bundled synthetic persona facts.

3. Confirm that SpacetimeDB is available and the configured database exists:

   ```bash
   spacetime login
   spacetime server ping maincloud
   spacetime list
   ```

   See the current [SpacetimeDB CLI reference](https://spacetimedb.com/docs/cli-reference/) for installation and command options.

   Confirm `credit-tank-state` is listed on `maincloud` and has the module from `spacetime/spacetimedb`. If this is a first-time setup and the database has not been published, run this from the repository root:

   ```bash
   spacetime publish credit-tank-state \
     --module-path ./spacetime/spacetimedb \
     --server maincloud \
     --no-config \
     --yes
   ```

   New databases install the cleanup schedule automatically. After upgrading an existing database, run the following once to enable the schedule and immediately remove expired sessions. It is safe to rerun:

   ```bash
   spacetime call credit-tank-state cleanup_expired_sessions \
     --server maincloud --no-config --yes
   ```

   Use the same database name and server in `.env`. Do not publish to a different database and expect the existing sessions to appear there. If you do not have SpacetimeDB access and only need a temporary local run, set `SESSION_STORE=memory`; state then disappears when FastAPI restarts.

4. Start FastAPI in one terminal. The `--env-file` path is relative to the current working directory, so run this from `backend/`:

   ```bash
   cd backend
   uvicorn app.main:app --reload --env-file ../.env
   ```

   The API is at `http://localhost:8000`; interactive API documentation is at `http://localhost:8000/docs`.

   Verify the selected modes at `http://localhost:8000/api/config`. `ai_provider` should be `xai` and `database` should be `spacetimedb` when their environment settings are present. This endpoint reports configuration selection; it does not verify that Grok credentials or the SpacetimeDB database are reachable.

5. Start the browser app in a second terminal:

   ```bash
   cd frontend
   npm ci
   npm run dev
   ```

   Open the Vite URL, usually `http://localhost:5173`. The frontend uses `http://localhost:8000` by default. To use a different API, copy `frontend/.env.example` to an ignored local env file such as `frontend/.env.local` and set `VITE_API_BASE`.

### Troubleshooting

- **`--env-file ../.env` does not exist:** this happens when the root `.env` has not been created, or when Uvicorn is launched from the wrong directory. Copy `.env.example` to the project root and run Uvicorn from `backend/` using the command above.
- **“Can't reach the game server”:** Vite on port 5173 serves the page; FastAPI on port 8000 serves game requests. Start both processes and check `http://localhost:8000/api/health`. If FastAPI uses another port or host, update `VITE_API_BASE` and the API's CORS `FRONTEND_ORIGINS` setting.
- **The browser shows offline dialogue:** `/api/config` reports `ai_provider: "offline"` when `GROK_API_KEY` is missing. Add the key to the root `.env` and restart FastAPI. The key is server-only; never put it in a `VITE_*` variable.
- **SpacetimeDB token or database errors:** if FastAPI exits during startup, run `spacetime login` or set `SPACETIMEDB_TOKEN`. If the API starts but session requests fail, confirm that the configured database and module exist on the configured server. On Render, set `SPACETIMEDB_TOKEN` in the service's secret environment settings.

## Dialogue and turn flow

### Question routing and investor behavior

Free-text questions use a case-insensitive substring keyword counter to select one of the five authored facts. Ties use topic-name ordering; an unmatched question gets a fixed unavailable-information response. This is not semantic question understanding. The investor follow-up topic is assigned by round: conditions, capacity, then collateral. The coverage chips record routed/discussed topics, not understanding or document sufficiency, and do not affect the score.

Each Grok request writes multiple fictional voices rather than running independent investor agents. It receives public business context, the current question where applicable, supplied facts, persona instructions, and at most six selected recent dialogue messages. Previous player questions and offer/round events are excluded from that recent context. The complete hidden profile and calculated grade are not sent. Investor sentiment does not determine offers; fixed backend rules select the bidder and terms from the full assessment.

### Grok and response length

The live provider is xAI Grok through the streaming Chat Completions API (`/v1/chat/completions`, `stream: true`). Claude is not used. The key is read by FastAPI from `GROK_API_KEY`. The default model is `grok-4.3` with reasoning disabled; model, reasoning effort, API base URL, and timeout can be set with the `GROK_*` variables in `.env.example`.

One question request generates four short, structured lines: the founder answers the player, one investor asks a focused follow-up, the founder answers using another supplied fact, and a second investor reacts. Founder lines are limited to 30 words; investor questions and reactions are checked for 4–18 words, and numbers in investor lines are rejected. The prompt directs founder answers to use only the verified fact supplied for each line, and code rejects numbers not present in that fact; it does not semantically verify every non-numeric claim. Personas guide tone and business focus, while the model is instructed not to decide whether to accept a deal. Without a key, the game retains a scripted offline fallback; it is shown as offline mode rather than represented as live Grok.

The request uses strict JSON Schema for the expected string fields and requests character limits; Python separately checks field names, types, word counts, numeric tokens, and the question's final `?`. It does not separately recheck character limits or the instruction that reactions contain one sentence. Each provider request sets `max_tokens: 420`. There is no automatic generation/validation retry, aggregate token or dollar budget, or per-user rate limiter. Failed turns can be retried without advancing the round, so the three-round cap alone does not bound total API spend.

### What players see while a question is answered

The question is added to the transcript immediately. While the API builds and validates the complete exchange, the browser receives server-sent progress and text-delta events. The current UI shows speaker/progress labels during that generation step; it does not yet paint the streamed Grok text deltas into the transcript. Once the API sends the saved session, the browser renders those canonical messages and plays them in order in the transcript and the 3D speech bubbles.

Each incoming line takes four seconds to reveal, followed by a two-second pause before the next line. The transcript follows the active line and retains the complete text; a 3D bubble appears above the current speaker. Reduced-motion mode displays the full transcript without timed playback. There is no standalone **Show All** control: during normal playback, offer, pass, and exit are disabled until the exchange finishes. In pitch review, **SHOW TRANSCRIPT & REVEAL DECISION** can reveal any remaining transcript and the founder's decision together.

The browser reads SSE frames through a fetch POST, without automatic reconnection, event-ID replay, or cross-connection deduplication. FastAPI sends `complete` after saving the turn. If that event is lost, the browser cannot infer whether the save committed; stream cancellation does not roll back a database transaction. The reading/playback lock is a browser rule, not a server-enforced waiting period.

### Pitch decisions

The player may offer, pass, or leave without asking. After one question, another question is blocked until a decision advances the round. Pass generates an additional three-line table exchange even if a question was already answered that round, and leaves a pending human offer active. A replacement offer withdraws the previous one; **I'm Out · Conversation Continues** withdraws the human's bids and lets the other investors finish. Pass/out requests use a normal response, so their generated exchanges arrive together after processing rather than as the question route's SSE stream.

An eligible offer can close round 1; AI offers begin in round 2, and three rounds is a maximum rather than guaranteed investigation time. Human bids must fit the remaining balance and 78%–150% of the ask. Deal eligibility also requires the grade's minimum target rate and, for grade 4, a secured flag. This does not recompute repayments at the offered rate or verify collateral. The founder then ranks eligible offers by capped funding, rate above the opening quote, and royalty; term and security are absent from that preference. Full rules are in [Scorecard Logic](docs/scorecard-logic.md#offer-eligibility-and-founder-selection).

Closing moves the pitch to review. The full current-pitch conversation remains available, but the public offer list filters out withdrawn/rejected offers rather than retaining every bid as a visible ledger. The `result` and final `scorecard` fields are withheld until reveal; accepted offer status and any human balance deduction already appear in review state, so outcome concealment is incomplete. After reveal, the result JSON also contains the risk grade even though the intermediate UI omits it. Advancing resets the active transcript; older conversation rows remain in SpacetimeDB but are not retrieved by the current app.

### What the score means

The engine assesses the complete hidden numeric profile regardless of the player's questions. It uses a fixed estimated payment of 3.4% of the original ask; the offered principal, rate, term, and royalties do not change that DSCR. Narrative warnings such as one-time revenue, low cash reserves, or an identity mismatch are not automatically translated into financial adjustments or mandatory review holds.

Decision Fit mainly rewards the winning human rate's proximity to a fixed target, or applies outcome-based points when the human does not fund. Underwriting Instinct combines that with illustrative simple-interest P&L. Question quality and coverage are not scored. Four current benchmark amounts are below the API's minimum bid. Offline checks also produced a score of 94 for an immediate P08 offer without questions and 90 for passing P05 without questions. These are limitations of the current teaching mechanics, documented with exact calculations in [Scorecard Logic](docs/scorecard-logic.md#reproducible-offline-examples), not evidence of lending competence or measured returns.

## SpacetimeDB and multiplayer groundwork

The default `SESSION_STORE=spacetime` persists sessions in the private `game_session` table. The private `conversation_message` table stores one ordered row per utterance, indexed by session, pitch, and sequence. FastAPI writes the session snapshot and transcript rows together through a transaction reducer, so they represent the same completed transition. A version value prevents concurrent stale session writes from silently overwriting each other. The current adapter restores and displays messages from `stateJson`; it does not query the separate message rows yet.

FastAPI still owns game rules, dialogue generation, and underwriting. The browser currently receives live updates through HTTP server-sent events, not a SpacetimeDB subscription. The indexed message rows prepare for ordered transcript queries but are not used by current reads; multiplayer is not complete because there are no authenticated rooms, player membership rules, or client subscriptions, and the tables stay private because session snapshots contain hidden borrower information.

For a local SpacetimeDB login, run `spacetime login`. The local backend can read the CLI token; a deployed API should receive `SPACETIMEDB_TOKEN` as a private environment secret. The database/module name is currently `credit-tank-state` for compatibility with the existing SpacetimeDB deployment. That infrastructure identifier is intentionally retained while the visible product name changes to Shrimp Tank; changing it would require a database migration or a new database.

The browser also retains the existing `credit-tank-*` local-storage keys so a session saved before the rename can still be resumed. Those are compatibility identifiers, not visible product branding.

## Deploy on Render

Create the API service first, then the static frontend. The frontend needs the API URL at build time, and the API needs the frontend origin for CORS.

### FastAPI web service

Create a Render **Web Service** connected to this repository:

| Setting | Value |
| --- | --- |
| Runtime | Python 3 |
| Root Directory | `backend` |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |

Copy the deployed API URL and set these variables in the API service's Environment page:

| Variable | Purpose |
| --- | --- |
| `FRONTEND_ORIGINS` | Exact URL of the deployed frontend, including `https://` |
| `GROK_API_KEY` | Required for live Grok personalities; without it, the game uses its scripted offline fallback |
| `GROK_MODEL`, `GROK_REASONING_EFFORT`, `GROK_BASE_URL`, `GROK_TIMEOUT_SECONDS` | Optional model settings; defaults are in `.env.example` |
| `SESSION_STORE` | `spacetime` for persistent state; `memory` only for temporary instances |
| `SPACETIMEDB_URI`, `SPACETIMEDB_DATABASE`, `SPACETIMEDB_TOKEN` | SpacetimeDB endpoint, existing database name, and owner token |

The API health endpoint is `<API URL>/api/health`; interactive documentation is at `<API URL>/docs`.

### Vite static site

Create a Render **Static Site** from the same repository:

| Setting | Value |
| --- | --- |
| Root Directory | `frontend` |
| Build Command | `npm ci && npm run build` |
| Publish Directory | `dist` |

Set `VITE_API_BASE` to the HTTPS URL of the FastAPI service. This value is embedded in the browser build and is public configuration; never put API keys or passwords in any `VITE_*` variable. If you are using already-created Render services, keep their actual generated hostnames even if they still contain the previous product name.

The deploy script can trigger both existing Render services using deploy hooks. One-time setup:

1. Copy `scripts/deploy-render.env.example` to `.deploy.env` and add the two Render deploy-hook URLs. `.deploy.env` is ignored by Git.
2. Ensure the current branch has been pushed and has a clean working tree. The script requires the current commit to match its upstream.
3. Log into SpacetimeDB locally so the script can publish `spacetime/spacetimedb` before deploying the API.
4. Preview, then deploy:

   ```bash
   ./scripts/deploy-render.sh --dry-run
   ./scripts/deploy-render.sh
   ```

Use `--api` or `--frontend` to deploy one service. The script does not create Render services or set their environment variables. See [Render's FastAPI guide](https://render.com/docs/deploy-fastapi), [Render Static Sites](https://render.com/docs/static-sites), and [Vite environment variables](https://vite.dev/guide/env-and-mode) for platform details.

The frontend and database-module npm lockfiles record resolved JavaScript dependencies; the Python requirements use version ranges rather than a resolved lockfile. The helper prints the checkout SHA, but its deploy-hook POST does not explicitly select that SHA or verify the revisions actually served by Render. Confirm service branch/revision settings and the published database module when checking a release. The local version inventory in [TECH-01](docs/methodology.md#questions-derived-from-that-stack) is not an inventory of the deployed services.

## Configuration reference

Use [.env.example](./.env.example) as the backend template and [frontend/.env.example](./frontend/.env.example) as the browser build template.

| Variable | Used by | Purpose |
| --- | --- | --- |
| `GROK_API_KEY` | Backend | Required for live Grok personalities; without it, the game uses the scripted offline fallback. Keep it server-side. |
| `GROK_MODEL`, `GROK_REASONING_EFFORT`, `GROK_BASE_URL`, `GROK_TIMEOUT_SECONDS` | Backend | Model and streaming request settings. |
| `SESSION_STORE` | Backend | `spacetime` by default; `memory` for temporary local development. |
| `SPACETIMEDB_URI`, `SPACETIMEDB_DATABASE`, `SPACETIMEDB_TOKEN` | Backend | Persistent database connection. Keep the owner token private. |
| `FRONTEND_ORIGINS` | Backend | Comma-separated browser origins allowed by CORS. |
| `VITE_API_BASE` | Frontend build | Public base URL used for FastAPI requests. |

The root `.gitignore` excludes local `.env*` files except checked-in `.env.example` templates, Python/Node dependencies, generated bundles, and SpacetimeDB's machine-local configuration.

`GROK_BASE_URL` selects the Chat Completions base; a trailing `/responses` is normalized to `/chat/completions`, not used to switch API families. Grok connections time out after 10 seconds; `GROK_TIMEOUT_SECONDS` defaults to 3,600 seconds for the other HTTPX timeout categories. Database requests use a 2-second connection timeout and 6 seconds for the other categories. These are operation/inactivity limits, not a deadline for the entire turn. `/api/health` and `/api/config` report service responsiveness and selected modes; neither tests a Grok request or database read/write. The session does not record a full history of the active model, prompts, code revision, or resolved dependency versions.

## Code structure

```text
.
├── frontend/
│   ├── src/main.ts               UI, API calls, dialogue pacing, transcript and speech bubble
│   ├── src/studio.ts             Three.js studio, shrimp actors, camera and opening sequence
│   ├── src/stage.ts              Stage interface/re-export
│   ├── src/style.css             Responsive overlay UI and viewport styling
│   ├── index.html                Browser document title and Vite entry point
│   └── package.json              Frontend scripts and dependencies
├── backend/
│   ├── app/main.py               FastAPI routes and session phase transitions
│   ├── app/main_types.py         Session data models
│   ├── app/catalog.py            Fictional pitches, hidden profiles, investor personas
│   ├── app/agents.py             Grok prompts, streaming parser, fact and length validation
│   ├── app/underwriting.py       Five Cs scores, offers, deal outcome, scorecard
│   ├── app/store.py              Session-store interface and in-memory adapter
│   ├── app/spacetime_store.py    SpacetimeDB persistence adapter
│   └── requirements.txt          Python dependencies
├── spacetime/
│   ├── spacetimedb/src/index.ts  Private tables and atomic session/transcript reducers
│   └── spacetime.json            SpacetimeDB module configuration
├── scripts/
│   ├── deploy-render.sh          Render deploy-hook workflow
│   └── deploy-render.env.example Deploy-hook template (no live secrets)
├── docs/
│   ├── data-model.md             SpacetimeDB schemas and design rationale
│   ├── scorecard-logic.md        Founder profiles, five Cs rubric, scorecard formulas
│   └── methodology.md            Focused questions and code-backed implementation answers
├── shark_tank_project_specs.md  Original project design brief
├── .env.example                 Backend environment template
└── README.md                    Setup, deployment, architecture, and issue history
```

### Request and state flow

1. The browser creates a session through FastAPI and renders the game state.
2. A question is submitted to `/api/sessions/{id}/question/stream`. FastAPI gets the verified facts and investor profiles, requests one structured Grok exchange, validates the lines, appends them to the transcript, and persists the session plus transcript rows.
3. The stream's `complete` event contains the saved public session. The browser re-renders that session, reveals each incoming line in the transcript while showing the matching 3D speaker bubble, then enables player decisions.
4. Offer, pass, and exit actions advance the deterministic game state. Closing a pitch enters `pitch_review`; a separate reveal request displays the founder's outcome. The final scorecard uses the five Cs rubric.

## Project boundaries

The focused [Methodology Questions and Answers](docs/methodology.md) explain the inspected data, financial methods, state, and gameplay. All retained questions have inline answers; missing evidence is identified explicitly. When an answer is added or revised there, the [documentation maintenance rule](docs/methodology.md#documentation-maintenance-for-methodology-answers) calls for checking and updating affected guides; it does not require unrelated README changes on other tasks.

- Founder credit facts are based on synthetic CRS persona examples bundled with the app. Business revenue, collateral, owner equity, and outcomes are fictional teaching values; no live CRS report is pulled during gameplay.
- The investor profiles are fictionalized teaching personas named after the canonical show investors; they are not official AI replicas or endorsements.
- The five Cs calculation is a transparent game mechanic, not calibrated lending policy.
- Prompts constrain Grok to supplied facts, and the backend rejects unsupported numbers in founder lines; deterministic Python rules handle underwriting and deal outcomes.
- The benchmark is a local loan formula; the app makes no Coinbase or x402 calls.
- The simulator is for fictional educational scenarios and does not make real credit decisions.
- The API currently targets sessions by ID without user authentication or session-owner checks. CORS is a browser-origin restriction, not user authorization. Database tables are private, but reducers do not check caller identity or room membership. Additional deployed access controls have not been verified; see the [access control boundary](docs/data-model.md#access-control-boundary).
