# Shrimp Tank

Shrimp Tank is a fictional, single-player B2B loan negotiation game. The player sits in the middle investor position, questions a founder, reviews the other investors' discussion, and decides whether to offer a loan, pass, or leave the pitch. A five Cs rubric explains the rules-based outcome. The game is educational and does not make real credit decisions.

The project has three parts:

- A Vite, TypeScript, and Three.js browser game with a procedural low-poly shrimp studio.
- A FastAPI service that owns session rules, Grok dialogue, and underwriting.
- A SpacetimeDB TypeScript module that stores session snapshots and ordered conversation messages.

The current game is single-player. The conversation table and persisted session model are groundwork for multiplayer; authenticated rooms, shared client subscriptions, and membership checks are not implemented yet.

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

**Challenges encountered:** Separate calls for each shark made the first question feel slow and made the table seem to be waiting on several independent agents. The implementation now asks Grok once for the complete four-line exchange. Another mismatch was that the browser showed “responding” status labels while the conversation text did not appear until later. The client now re-renders the saved exchange as soon as the stream completes and plays it in sync with the speech bubbles. During Grok generation, it still shows progress labels rather than partial dialogue; timed playback starts after the full response is validated and saved.

### SpacetimeDB

SpacetimeDB stores durable session snapshots and an indexed copy of the conversation. The `game_session` row holds the complete serialized game state; `conversation_message` holds one ordered row per message. Both are written in the same reducer transaction. The tables are private because the session snapshot contains hidden borrower profiles. The current FastAPI adapter restores the transcript from the session snapshot; it writes the message rows but does not query them. The browser receives dialogue over FastAPI server-sent events and does not connect to SpacetimeDB directly, so multiplayer rooms and live database subscriptions remain future work.

The field definitions, payload shape, indexes, reducer behavior, privacy choices, and rationale for each table are documented in [SpacetimeDB Data Model](docs/data-model.md).

**Challenges encountered:** Local FastAPI startup requires a SpacetimeDB token, supplied by `spacetime login` or `SPACETIMEDB_TOKEN`. The backend does not ping the database during startup, so a missing or unpublished database appears later as a failed persistence request. Deployed FastAPI needs the owner token as a server secret. The tables are private because the session row contains hidden profiles and unrevealed outcomes. A separate conversation table provides an indexed path for future transcript queries; the current adapter restores the transcript from the session snapshot and does not read the message rows. This is persistence groundwork, not multiplayer synchronization: FastAPI remains the state owner and the browser does not subscribe to SpacetimeDB yet.

### CRS CalHacks MCP server and CRS sandbox

The npm package [`@crscreditapi/crs-calhacks-mcp-server`](https://www.npmjs.com/package/@crscreditapi/crs-calhacks-mcp-server) is used during development as a reference and discovery tool. We use tools such as `get_personas` and `get_product_guide` to inspect synthetic applicants and product details; `get_api_schema` and `get_test_data` help check product fields and canned cases. That information informed the local synthetic persona catalog.

The deployed game does **not** call the MCP server or CRS APIs at runtime. MCP is the developer/agent interface; the FastAPI app has no MCP client dependency. CRS persona information was used to construct the bundled fictional founder profiles, so gameplay does not require CRS credentials and does not make credit-report requests.

The profile path is:

1. MCP persona information provides synthetic examples that inform the founder credit profiles.
2. `backend/app/catalog.py` pairs 19 playable synthetic credit personas with fictional founders, businesses, revenue, repayment capacity, owner equity, collateral, and market conditions. P14's deceased-file scenario is excluded, leaving 19 playable cases from the 20-persona pool.
3. Bundled credit facts and business metrics provide the evidence used by Grok dialogue and the deterministic underwriting model.

CRS supplies synthetic persona examples for the bundled catalog; the fictional business and five Cs teaching profile are curated locally. No real applicant data is used.

**Challenges encountered:** The MCP guide covers several CRS products, and the initial design added an optional direct sandbox-report pull during a pitch. That feature required credentials and could update the credit score mid-game, adding a second source of state for the underwriting decision. To keep the game simpler, the report panel, runtime connector, endpoint, and credential settings have been removed. CRS persona examples remain bundled as synthetic scenario facts; Grok phrases those supplied facts conversationally, and the backend rejects founder answers with numbers absent from the selected fact. That check does not prove every non-numeric claim is supported, so the prompt remains an important safeguard.

### TypeScript, Vite, and Three.js

TypeScript and Vite build the browser client; Three.js creates the shrimp actors and studio from code-generated geometry, materials, and lights.

**Challenges encountered:** The stage has appeared as a mostly empty color panel during layout changes, and some camera/UI arrangements obscured the environment or the speech bubbles. The scene was rebuilt toward a larger Shark Tank-inspired set, the investor shrimps were spaced around the player, and the camera now stays forward-facing with side-to-side drag limits. Door frames briefly looked like bars across the presenter's route; a thin cyan horizon line in the city-window texture can still be mistaken for one. An external shrimp model was tried and then reverted, so the current low-poly characters remain procedural. Long speech bubbles and a tall conversation panel also reduced readability and covered the set; the transcript now retains the full line while the bubble scrolls, and the wide conversation panel has a shorter height. Overlay text, live announcements, and reduced-motion behavior were refined alongside the scene.

### Python, FastAPI, HTTPX, and Render

FastAPI owns session transitions and underwriting. HTTPX calls Grok from the server; the SpacetimeDB adapter persists game state. Render hosts the API and static frontend; `scripts/deploy-render.sh` publishes the SpacetimeDB module and triggers the existing Render services.

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

### Grok and response length

The live provider is xAI Grok through the streaming Chat Completions API (`/v1/chat/completions`, `stream: true`). Claude is not used. The key is read by FastAPI from `GROK_API_KEY`. The default model is `grok-4.3` with reasoning disabled; model, reasoning effort, API base URL, and timeout can be set with the `GROK_*` variables in `.env.example`.

One question request generates four short, structured lines: the founder answers the player, one investor asks a focused follow-up, the founder answers using another supplied fact, and a second investor reacts. Founder lines are limited to 30 words; investor questions and reactions are checked for 4–18 words, and numbers in investor lines are rejected. The prompt directs founder answers to use only the verified fact supplied for each line, and code rejects numbers not present in that fact; it does not semantically verify every non-numeric claim. Personas guide tone and business focus, while the model is instructed not to decide whether to accept a deal. Without a key, the game retains a scripted offline fallback; it is shown as offline mode rather than represented as live Grok.

### What players see while a question is answered

The question is added to the transcript immediately. While the API builds and validates the complete exchange, the browser receives server-sent progress and text-delta events. The current UI shows speaker/progress labels during that generation step; it does not yet paint the streamed Grok text deltas into the transcript. Once the API sends the saved session, the browser renders those canonical messages and plays them in order in the transcript and the 3D speech bubbles.

Each incoming line takes four seconds to reveal, followed by a two-second pause before the next line. The transcript follows the active line and retains the complete text; a 3D bubble appears above the current speaker. Reduced-motion mode displays the full transcript without timed playback. There is no standalone **Show All** control: during normal playback, offer, pass, and exit are disabled until the exchange finishes. In pitch review, **SHOW TRANSCRIPT & REVEAL DECISION** can reveal any remaining transcript and the founder's decision together.

### Pitch decisions

After the player asks one question in a round, that round must be closed with an offer, pass, or **I'm Out · Table Continues**. The exit action removes the player from bidding but does not terminate the session: the other investors can finish their discussion and make eligible offers.

Closing a pitch moves it to a review phase. The transcript and offers stay visible; the founder's selection remains hidden until the player selects the reveal control. The result then shows whether the founder accepted the player's offer, chose another investor, or made no deal. The player can continue to the next pitch from the result screen.

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
│   └── data-model.md             SpacetimeDB schemas and design rationale
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

- Founder credit facts are based on synthetic CRS persona examples bundled with the app. Business revenue, collateral, owner equity, and outcomes are fictional teaching values; no live CRS report is pulled during gameplay.
- The investor profiles are fictionalized teaching personas named after the canonical show investors; they are not official AI replicas or endorsements.
- The five Cs calculation is a transparent game mechanic, not calibrated lending policy.
- Prompts constrain Grok to supplied facts, and the backend rejects unsupported numbers in founder lines; deterministic Python rules handle underwriting and deal outcomes.
- The benchmark is a local loan formula; the app makes no Coinbase or x402 calls.
- The simulator is for fictional educational scenarios and does not make real credit decisions.
