# The Credit Tank

The Credit Tank is a single-player B2B loan negotiation simulator. You take the middle investor seat, question fictional founders, build loan offers, and compare your choices with a transparent five Cs teaching rubric.

The project has two deployable parts:

- A Vite + Three.js browser application.
- A FastAPI service that owns sessions, underwriting, dialogue, and optional CRS requests.

The 3D studio is procedural. Its low-poly shrimp characters and fluorescent yellow set do not require downloaded model assets.

## Deploy on Render

Deploy the API first, then the frontend. The static frontend needs the public API URL at build time, and the API needs the frontend origin for CORS.

### Before you start

1. Create a GitHub repository and push this project to it.

2. Create a Render account and connect it to that repository.

3. Keep .env files and API keys out of Git. The existing .gitignore already excludes .env.

### 1. Deploy the FastAPI service

In Render, select **New** → **Web Service**, then select the repository. Use these values:

| Render setting | Value |
| --- | --- |
| Runtime | Python 3 |
| Root Directory | backend |
| Build Command | pip install -r requirements.txt |
| Start Command | uvicorn app.main:app --host 0.0.0.0 --port $PORT |

After Render completes the first deploy, copy the generated API URL. It will resemble https://credit-tank-api.onrender.com.

Set environment variables in the API service's **Environment** section:

| Variable | Required | Value |
| --- | --- | --- |
| FRONTEND_ORIGINS | After the frontend is deployed | Exact frontend URL, for example https://credit-tank.onrender.com |
| GROK_API_KEY | Optional | xAI API key; setting it enables live Grok dialogue |
| GROK_MODEL / GROK_REASONING_EFFORT / GROK_BASE_URL / GROK_TIMEOUT_SECONDS | No | Defaults to `grok-4.3`, no reasoning, `https://api.x.ai/v1`, and 3600 seconds |
| CRS_USERNAME / CRS_PASSWORD | Only for sandbox report pulls | CRS sandbox credentials |
| SESSION_STORE | Yes | `spacetime` (use `memory` only for isolated tests) |
| SPACETIMEDB_URI | Yes | `https://maincloud.spacetimedb.com` |
| SPACETIMEDB_DATABASE | Yes | `credit-tank-state` |
| SPACETIMEDB_TOKEN | Yes | Database-owner token; add it as a secret, never as a `VITE_*` value |

The API health endpoint is https://YOUR-API-URL/api/health. Its interactive API documentation is https://YOUR-API-URL/docs.

### 2. Deploy the Vite frontend

In Render, select **New** → **Static Site**, then choose the same repository. Use these values:

| Render setting | Value |
| --- | --- |
| Root Directory | frontend |
| Build Command | npm ci && npm run build |
| Publish Directory | dist |

Add this environment variable before the initial deploy:

| Variable | Value |
| --- | --- |
| VITE_API_BASE | The HTTPS API URL from step 1, for example https://credit-tank-api.onrender.com |

Render will create an onrender.com URL for the static frontend. Copy that exact URL into the API service's FRONTEND_ORIGINS value, then redeploy the API.

Open the frontend URL, start a one-pitch session, and confirm that it can create a session. If the browser says it cannot reach the game server:

- Check that VITE_API_BASE contains the API URL and has no trailing slash.
- Check that FRONTEND_ORIGINS matches the frontend URL exactly.
- Check the API health endpoint in a browser.

VITE_API_BASE is public build configuration. Vite includes every VITE_* value in the browser bundle, so never put CRS, Grok, or other credentials in one.

For local Grok dialogue, put `GROK_API_KEY=your-key` in the project-root `.env` file. That file is git-ignored and loaded by the documented Uvicorn command. Restart FastAPI after editing it. The backend calls xAI's streaming Chat Completions API with `stream: true`, using Grok 4.3 with reasoning disabled by default for responsive dialogue; set `GROK_MODEL=grok-4.7` and `GROK_REASONING_EFFORT=low` to opt into the previous model. The game displays the question immediately, shows a progress state, and renders each response line as it arrives. `GROK_TIMEOUT_SECONDS` defaults to 3600. The key never goes to the browser. Without a key, the game shows its offline scripted fallback.

### Deploy both services with the script

After the one-time Render setup above, the repository script performs local preflight checks and triggers both existing Render services. It uses deploy hooks, so it does not need a Render API key.

1. Copy the deploy-hook template and paste the two secret hook URLs from each Render service's **Settings** page:

   ~~~bash
   cp scripts/deploy-render.env.example .deploy.env
   ~~~

2. Make the script executable once:

   ~~~bash
   chmod +x scripts/deploy-render.sh
   ~~~

3. Commit and push the changes. The script intentionally deploys only when the working tree is clean and the current commit exactly matches its upstream branch.

4. Preview the actions, then deploy:

   ~~~bash
   ./scripts/deploy-render.sh --dry-run
   ./scripts/deploy-render.sh
   ~~~

Use --api or --frontend to deploy only one service. The script does not create Render services or set secrets; keep those actions in the Render dashboard. Deploy hooks trigger the currently linked branch without changing Render's automatic-deploy setting.

### Custom domain

Add the custom domain to the Render Static Site first. Then set FRONTEND_ORIGINS on the API to that exact https origin and redeploy the API. If the frontend needs a new API URL, update VITE_API_BASE and redeploy the Static Site.

### Persistent game state

Game sessions are stored in the private `game_session` table of the published `credit-tank-state` SpacetimeDB database. FastAPI retains the game rules and writes each completed transition through a transactional `upsert_session` reducer, so sessions survive API restarts and deploys. The table is private because it contains hidden fictional borrower profiles.

For local development, run `spacetime login` once, then start FastAPI with the local root `.env` configuration:

~~~bash
cd backend
uvicorn app.main:app --reload --env-file ../.env
~~~

The local configuration relies on the logged-in CLI token without copying it into `.env`. On Render, set `SPACETIMEDB_TOKEN` from `spacetime login show --token` as a secret environment variable. The deployment script publishes `spacetime/spacetimedb` before it triggers the API deploy.

### Deployment limitations

- Presenters are fictional businesses layered over 19 fixed CRS sandbox credit personas. The deceased-file case is not playable; criminal and eviction records are not used as loan-risk criteria. Optional report pulls send only the exact published synthetic request bodies. Set CRS credentials only in the API service environment.
- Offline dialogue is fully deployable without third-party credentials.

Render's FastAPI guide uses a Web Service with a uvicorn command bound to $PORT, and its Static Site guide covers repository builds and publishing. See [Render's FastAPI deployment guide](https://render.com/docs/deploy-fastapi), [Render Static Sites](https://render.com/docs/static-sites), and [Vite environment variables](https://vite.dev/guide/env-and-mode) for the current platform details.

## Run locally

Requirements: Python 3.11+ and Node.js 20.19+.

1. From the project root, create a virtual environment and install backend packages:

   ~~~bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r backend/requirements.txt
   ~~~

2. Start the API in one terminal:

   ~~~bash
   cd backend
   uvicorn app.main:app --reload
   ~~~

   Persistent SpacetimeDB state is enabled by default. Run `spacetime login` once, then use the root `.env` file (or copy `.env.example` when working from a fresh clone):

   ~~~bash
   uvicorn app.main:app --reload --env-file ../.env
   ~~~

3. Start the frontend in another terminal:

   ~~~bash
   cd frontend
   npm install
   npm run dev
   ~~~

Open the URL Vite prints, usually http://localhost:5173. The API docs are at http://localhost:8000/docs.

## Configuration reference

| Location | Variable | Purpose |
| --- | --- | --- |
| API environment | FRONTEND_ORIGINS | Comma-separated browser origins allowed to call the API. Keep the public frontend URL here in production. |
| API environment | GROK_API_KEY | Optional server-side xAI key. Its presence enables live Grok dialogue. |
| API environment | GROK_MODEL, GROK_REASONING_EFFORT, GROK_BASE_URL, GROK_TIMEOUT_SECONDS | Optional model, reasoning effort, xAI API base URL, and streaming request timeout (3600 seconds by default). |
| API environment | CRS_USERNAME, CRS_PASSWORD | Optional server-side CRS sandbox credentials. |
| API environment | SESSION_STORE | `spacetime` by default; set to `memory` only for isolated development tests. |
| API environment | SPACETIMEDB_URI, SPACETIMEDB_DATABASE | Maincloud host and database name used by the session adapter. |
| API environment | SPACETIMEDB_TOKEN | Owner token used by deployed FastAPI to access the private session table. Never expose it to the browser. |
| Frontend build environment | VITE_API_BASE | Public API base URL used by the browser. It is compiled into the frontend. |

Use [.env.example](./.env.example) as the API configuration template and [frontend/.env.example](./frontend/.env.example) as the frontend build configuration template.

## Code structure

~~~text
.
├── frontend/                     Browser application
│   ├── src/main.ts               UI rendering, API calls, dialogue pacing, player speech bubble
│   ├── src/studio.ts             Three.js shrimp set, first-person camera, NPC speech bubbles
│   ├── src/stage.ts              Small re-export boundary for the studio
│   ├── src/style.css             Responsive dashboard and 3D viewport styling
│   ├── index.html                Vite entry document and font setup
│   └── package.json              Vite, TypeScript, and Three.js commands/dependencies
├── backend/                      FastAPI application
│   ├── app/main.py               HTTP routes, CORS configuration, session phase transitions
│   ├── app/main_types.py         Session data models
│   ├── app/catalog.py            Fictional business cases built on CRS synthetic credit personas
│   ├── app/agents.py             Question classification and optional model dialogue phrasing
│   ├── app/underwriting.py       Five Cs rubric, offer checks, benchmark, scorecard
│   ├── app/crs.py                Exact-body CRS sandbox connector for playable personas
│   ├── app/store.py              Session storage protocol and explicit memory-only test adapter
│   ├── app/spacetime_store.py    Private-table SpacetimeDB persistence adapter
│   └── requirements.txt          Python dependencies
├── spacetime/
│   ├── spacetimedb/src/index.ts  Private session table and upsert/delete reducers
│   └── spacetime.json            Maincloud module configuration
├── scripts/
│   ├── deploy-render.sh           Preflight checks and Render deploy-hook trigger
│   └── deploy-render.env.example  Secret deploy-hook configuration template
├── shark_tank_project_specs.md   Original project design brief
├── .env.example                  API environment variable template
└── README.md                     Local development, deployment, and architecture guide
~~~

### Browser flow

main.ts requests a session from the API, renders the dashboard, and sends questions or offers back to FastAPI. It dynamically loads the Three.js scene so the base interface can render before the 3D module finishes loading. A submitted question appears immediately with a progress indicator; the transcript and speaker bubble then update from SSE text deltas. After a player question, the UI explicitly requires an offer, pass, or exit to close that round. Choosing **I'M OUT · TABLE CONTINUES** removes only the player from bidding: the remaining investors finish their questions, table reactions, and eligible offers. Once a pitch closes, the full transcript remains available in a review state before the player chooses to reveal the founder's decision.

studio.ts owns the WebGL renderer. It creates the low-poly shrimp actors, fluorescent room, first-person center-seat view, and speech sprites above NPCs. The player question appears as a screen-space bubble above the desk because the player has no visible third-person model.

### API flow

main.py exposes /api/sessions and the routes that advance questions, decisions, the decision-reveal step, CRS pulls, and scorecards. It serializes changes to each session with a per-session lock. A completed pitch moves to `pitch_review` with its result withheld; `POST /api/sessions/{session_id}/reveal` then publishes the decision and moves it to `pitch_result`.

catalog.py holds public pitch descriptions, hidden fictional borrower profiles, and named fictionalized teaching personas for Kevin O'Leary, Lori Greiner, and Mark Cuban. A player question uses one Grok request to generate the founder's two answers and the two investors' lines; it does not call Grok separately for each judge. By default, agents.py uses Grok 4.3 with reasoning disabled for low-latency dialogue. The `/question/stream` route forwards response deltas to the browser as server-sent events. Founder answers are checked against the supplied verified facts, and investor lines remain capped at 18 words. Without a key, a scripted offline fallback remains available. underwriting.py keeps the five Cs rubric and deal outcomes deterministic.

spacetime_store.py persists session state in the private `game_session` table and each utterance in the indexed, private `conversation_message` table. A reducer commits both together; the message rows retain session, pitch, and sequence fields for ordered transcript replay. Live single-player display uses SSE, so it does not wait on database polling or write one database row per token. The transcript table is private until multiplayer identity and membership checks are implemented. Set `SESSION_STORE=memory` only when an isolated in-memory test is specifically needed.

## Design boundaries

- CRS reports in this project are consumer-credit sandbox reports for fictional founders. Business cash flow, collateral, owner equity, and conditions are separate fictional teaching data.
- The five Cs formula is a reproducible game mechanic, not calibrated lending policy.
- The model integration receives the current question and one approved fact. It does not request or expose hidden chain-of-thought.
- The benchmark is a local loan-specific formula. The app makes no Coinbase or x402 calls.
- The simulator is for fictional educational cases only; it does not make real credit decisions.
