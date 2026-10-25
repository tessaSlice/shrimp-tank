import "./style.css";
import type { Stage } from "./stage";

type Message = { id: string; speaker: string; text: string; kind: string; round: number; player_id?: string };
type PlayerState = { id: string; name: string; is_host?: boolean; balance?: number; starting_capital?: number; out: boolean; scorecard?: any };
type OfferDraft = { amount: number; rate: number; royalty: number; termMonths: number; secured: boolean };
type GameState = {
  id: string; phase: string; difficulty: string; total_pitches: number; pitch_index: number; round: number;
  quiet_rounds: number; quiet_round_limit: number;
  balance: number; starting_capital: number; pitch: any; messages: Message[]; disclosures: string[]; offers: any[];
  sharks: any[]; investor_portfolios: any[]; question_asked: boolean; human_out: boolean; result: any; scorecard: any; ai_mode: string;
  immediate_acceptance?: boolean;
  players?: PlayerState[]; self_player_id?: string; current_player_id?: string; current_player_name?: string; is_my_turn?: boolean;
};

const ui = document.querySelector<HTMLElement>("#ui")!;
let stage: Stage | null = null;
const stageReady = import("./stage").then(({ createStage }) => {
  const landingScene = document.querySelector<HTMLElement>(".hero-scene");
  const initialHost = game
    ? document.querySelector<HTMLElement>("#game-stage") || document.querySelector<HTMLElement>("#stage")!
    : landingScene || document.querySelector<HTMLElement>("#stage")!;
  stage = createStage(initialHost);
  if (game) {
    stage?.setPitch(game.pitch.archetype, game.pitch.company);
    const gameStage = document.querySelector<HTMLElement>("#game-stage");
    if (gameStage) stage?.mount(gameStage);
  } else {
    const heroScene = document.querySelector<HTMLElement>(".hero-scene");
    if (heroScene) stage?.mount(heroScene);
  }
  return stage;
}).catch(() => null);
const API_BASE = import.meta.env.VITE_API_BASE || `${location.protocol}//${location.hostname || "localhost"}:8000`;
let game: GameState | null = null;
let roomSocket: WebSocket | null = null;
let roomSessionId: string | null = null;
let roomReconnectTimer = 0;
let roomHeartbeatTimer = 0;
let pendingRoomState: GameState | null = null;
let roomRetryDelay = 1200;
let selectedDifficulty = "medium";
let selectedPitchCount = 4;
let busy = false;
let reviewingOffer = false;
let offerEditorOpen = false;
let offerDraft: OfferDraft | null = null;
let readingUntil = 0;
let toastTimer = 0;
let speechTimer = 0;
let speechToken = 0;
let speechActive = false;
let readingTickTimer = 0;
let wasReadingLocked = false;
const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
const SPEECH_BUBBLE_DURATION_MS = 4000;
const SPEECH_BUBBLE_HOLD_MS = 1000;
const SPEECH_BUBBLE_GAP_MS = 2000;

function roomClientId() {
  let id = sessionStorage.getItem("shrimp-tank-room-client");
  if (!id) {
    id = globalThis.crypto?.randomUUID?.() || `tab-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    sessionStorage.setItem("shrimp-tank-room-client", id);
  }
  return id;
}

function personalizeGameState(state: GameState): GameState {
  const player = state.players?.find((candidate) => candidate.id === state.self_player_id)
    ?? (state.players?.length === 1 ? state.players[0] : undefined);
  if (!player) return { ...state, self_player_id: state.self_player_id || "human_user", is_my_turn: state.is_my_turn ?? true };
  return {
    ...state,
    self_player_id: player.id,
    balance: player.balance ?? state.balance,
    starting_capital: player.starting_capital ?? state.starting_capital,
    human_out: player.out,
    is_my_turn: state.current_player_id === player.id && !player.out,
    scorecard: player.scorecard ?? state.scorecard,
  };
}

const money = (value: number) => new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(value || 0);
const esc = (value: unknown) => String(value ?? "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]!);

async function api<T = any>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", "X-Room-Client-ID": roomClientId(), ...(init.headers || {}) },
    });
  } catch {
    throw new Error("Can't reach the game server. Start FastAPI on port 8000 and try again.");
  }
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || `Request failed (${response.status}).`);
  return body as T;
}

async function streamQuestion(
  sessionId: string,
  question: string,
  onStart: (message: { field: string; speaker: string; kind: string; round: number }) => void,
  onDelta: (field: string, text: string) => void,
  onProgress: (message: string) => void,
): Promise<GameState> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}/api/sessions/${encodeURIComponent(sessionId)}/question/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream", "X-Room-Client-ID": roomClientId() },
      body: JSON.stringify({ question }),
    });
  } catch {
    throw new Error("Can't reach the game server. Start FastAPI on port 8000 and try again.");
  }
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed (${response.status}).`);
  }
  if (!response.body) throw new Error("The game server did not open a dialogue stream. Please retry.");

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let completed: GameState | null = null;
  const processFrame = (frame: string) => {
    let event = "message";
    const data: string[] = [];
    for (const line of frame.split("\n")) {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      else if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
    }
    if (!data.length) return;
    const payload = JSON.parse(data.join("\n"));
    if (event === "message_start") onStart(payload);
    else if (event === "delta") onDelta(payload.field, payload.text);
    else if (event === "progress") onProgress(payload.message);
    else if (event === "complete") completed = payload as GameState;
    else if (event === "error") throw new Error(payload.detail || "The dialogue stream failed. Please retry.");
  };

  try {
    while (true) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value, { stream: !done });
      buffer = buffer.replace(/\r\n/g, "\n");
      let boundary = buffer.indexOf("\n\n");
      while (boundary >= 0) {
        processFrame(buffer.slice(0, boundary));
        buffer = buffer.slice(boundary + 2);
        if (completed) {
          await reader.cancel();
          return completed;
        }
        boundary = buffer.indexOf("\n\n");
      }
      if (done) break;
    }
  } catch (error) {
    await reader.cancel().catch(() => undefined);
    if (error instanceof SyntaxError) throw new Error("The game server sent an invalid dialogue event. Please retry.");
    throw error;
  }
  if (completed) return completed;
  throw new Error("The dialogue stream ended before the turn was saved. Please retry.");
}

function setRoomPresence(count: number | null) {
  const label = document.querySelector<HTMLElement>("#room-presence");
  if (!label) return;
  label.textContent = count === null ? "RECONNECTING…" : `${count} ${count === 1 ? "CLIENT" : "CLIENTS"}`;
  label.dataset.connected = String(count !== null);
}

function disconnectRoom() {
  roomSessionId = null;
  pendingRoomState = null;
  window.clearTimeout(roomReconnectTimer);
  window.clearInterval(roomHeartbeatTimer);
  const socket = roomSocket;
  roomSocket = null;
  if (socket && socket.readyState < WebSocket.CLOSING) socket.close();
}

function connectRoom(sessionId: string) {
  if (roomSessionId !== sessionId) {
    disconnectRoom();
    roomSessionId = sessionId;
    roomRetryDelay = 1200;
  }
  if (roomSocket && (roomSocket.readyState === WebSocket.OPEN || roomSocket.readyState === WebSocket.CONNECTING)) return;
  window.clearTimeout(roomReconnectTimer);
  setRoomPresence(null);
  const endpoint = new URL(`/api/sessions/${encodeURIComponent(sessionId)}/live`, API_BASE);
  endpoint.protocol = endpoint.protocol === "https:" ? "wss:" : "ws:";
  endpoint.searchParams.set("client_id", roomClientId());
  const socket = new WebSocket(endpoint);
  roomSocket = socket;
  socket.addEventListener("open", () => {
    if (roomSocket !== socket) return;
    roomRetryDelay = 1200;
    roomHeartbeatTimer = window.setInterval(() => {
      if (socket.readyState === WebSocket.OPEN) socket.send("ping");
    }, 20000);
  });
  socket.addEventListener("message", (event) => {
    if (roomSocket !== socket) return;
    let message: any;
    try { message = JSON.parse(event.data); } catch { return; }
    if (message.type === "presence") setRoomPresence(Number(message.count) || 0);
    else if (message.type === "state") receiveRoomState(message.state as GameState);
    else if (message.type === "room_closed") {
      localStorage.removeItem("credit-tank-session");
      disconnectRoom();
      renderLanding();
      toast(message.message || "The shared game was closed.");
    }
  });
  socket.addEventListener("close", (event) => {
    if (roomSocket !== socket || roomSessionId !== sessionId) return;
    roomSocket = null;
    window.clearInterval(roomHeartbeatTimer);
    setRoomPresence(null);
    if (event.code === 1008) {
      const label = document.querySelector<HTMLElement>("#room-presence");
      if (label) label.textContent = "ROOM UNAVAILABLE";
      toast("The live room rejected this connection. Check the invite and the backend's FRONTEND_ORIGINS setting.");
      return;
    }
    roomReconnectTimer = window.setTimeout(() => {
      if (roomSessionId === sessionId) connectRoom(sessionId);
    }, roomRetryDelay);
    roomRetryDelay = Math.min(10000, Math.round(roomRetryDelay * 1.7));
  });
  socket.addEventListener("error", () => socket.close());
}

function receiveRoomState(state: GameState) {
  state = personalizeGameState(state);
  if (!state || !game || state.id !== game.id) return;
  if (isOlderRoomState(state, game)) return;
  if (JSON.stringify(state) === JSON.stringify(game)) return;
  if (busy || speechActive) {
    if (!pendingRoomState || !isOlderRoomState(state, pendingRoomState)) pendingRoomState = state;
    return;
  }
  applyRoomState(state);
}

function isOlderRoomState(candidate: GameState, current: GameState) {
  if (candidate.pitch_index !== current.pitch_index) return candidate.pitch_index < current.pitch_index;
  if (candidate.round !== current.round) return candidate.round < current.round;
  const phaseOrder: Record<string, number> = { investigate: 0, pitch_review: 1, pitch_result: 2, complete: 3 };
  const candidatePhase = phaseOrder[candidate.phase] ?? 0;
  const currentPhase = phaseOrder[current.phase] ?? 0;
  if (candidatePhase !== currentPhase) return candidatePhase < currentPhase;
  return candidate.messages.length < current.messages.length;
}

function applyRoomState(state: GameState) {
  state = personalizeGameState(state);
  if (!game || state.id !== game.id) return;
  if (isOlderRoomState(state, game)) return;
  const priorMessages = new Set(game.messages.map((message) => message.id));
  const newMessages = state.messages.filter((message) => !priorMessages.has(message.id));
  game = state;
  localStorage.setItem("credit-tank-session", state.id);
  if (state.phase === "complete") renderScorecard();
  else if (state.phase === "pitch_result") renderPitchResult();
  else renderGame(newMessages);
}

function flushPendingRoomState() {
  if (busy || speechActive || !pendingRoomState) return;
  const state = pendingRoomState;
  pendingRoomState = null;
  applyRoomState(state);
}

async function inviteToRoom() {
  if (!game) return;
  const invite = new URL(location.href);
  invite.hash = new URLSearchParams({ room: game.id }).toString();
  let copied = false;
  try {
    await navigator.clipboard.writeText(invite.toString());
    copied = true;
  } catch {
    copied = window.prompt("Copy this shared game link:", invite.toString()) !== null;
  }
  if (!copied) { toast("Invite link was not copied."); return; }
  const isLocalhost = ["localhost", "127.0.0.1", "0.0.0.0"].includes(location.hostname);
  toast(isLocalhost
    ? "Invite copied. Other devices need this site opened with your computer's LAN IP instead of localhost."
    : "Shared game invite copied. Other devices can join on the same network.", "success");
}

function toast(message: string, kind = "error") {
  const holder = document.querySelector<HTMLElement>("#toast");
  if (!holder) return;
  holder.textContent = message;
  holder.className = `toast show ${kind}`;
  window.clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => { holder.className = "toast"; }, 4200);
}

function announce(message: string) {
  const holder = document.querySelector<HTMLElement>("#announcer");
  if (!holder) return;
  holder.textContent = "";
  window.setTimeout(() => { holder.textContent = message; }, 25);
}

function dialogueDuration(messages: Message[]) {
  if (reducedMotion.matches) return 0;
  const incoming = messages.filter((message) => message.kind !== "question");
  const questionPause = messages.some((message) => message.kind === "question") ? 850 : 0;
  return questionPause + incoming.length * (SPEECH_BUBBLE_DURATION_MS + SPEECH_BUBBLE_HOLD_MS) + Math.max(0, incoming.length - 1) * SPEECH_BUBBLE_GAP_MS;
}

function holdForDialogue(messages: Message[]) {
  readingUntil = Date.now() + dialogueDuration(messages);
}

function isLocalPlayerMessage(message: Message) {
  if (message.player_id) return message.player_id === game?.self_player_id;
  return message.speaker === "You";
}

function stopSpeech() {
  window.clearTimeout(speechTimer);
  speechToken += 1;
  speechActive = false;
  stage?.setSpeaker(null);
  const bubble = document.querySelector<HTMLElement>("#player-speech-bubble");
  const text = bubble?.querySelector<HTMLElement>("p");
  if (text) text.textContent = "";
  if (bubble) bubble.hidden = true;
}

function showPlayerSpeech(text: string) {
  const bubble = document.querySelector<HTMLElement>("#player-speech-bubble");
  const body = bubble?.querySelector<HTMLElement>("p");
  if (body) body.textContent = text;
  if (bubble) bubble.hidden = !text;
}

function showFullTranscript() {
  stopSpeech();
  if (game) {
    for (const message of game.messages) {
      const article = document.getElementById(`message-${message.id}`);
      if (article) article.hidden = false;
      article?.classList.remove("pending-message", "speaking");
      const body = article?.querySelector<HTMLElement>(".message-text, .stage-message-text");
      if (body) body.textContent = message.text;
    }
  }
  readingUntil = 0;
  displayReadingLock();
  announce("All current dialogue is now visible.");
}

function playDialogue(messages: Message[]) {
  const token = speechToken;
  const playerQuestion = [...messages].reverse().find((message) => message.kind === "question");
  if (playerQuestion) {
    const isMine = isLocalPlayerMessage(playerQuestion);
    showPlayerSpeech(isMine ? playerQuestion.text : "");
    stage?.setSpeaker(isMine ? -1 : null);
    announce(`${playerQuestion.speaker} asked: ${playerQuestion.text}`);
  }
  const incoming = messages.filter((message) => message.kind !== "question");
  if (reducedMotion.matches) {
    const playerOffer = [...messages].reverse().find((message) => isLocalPlayerMessage(message) && message.kind === "offer");
    if (!playerQuestion && playerOffer) showPlayerSpeech(playerOffer.text);
    if (playerQuestion || playerOffer) {
      speechTimer = window.setTimeout(() => {
        if (token === speechToken) showPlayerSpeech("");
        flushPendingRoomState();
      }, SPEECH_BUBBLE_HOLD_MS);
    }
    else flushPendingRoomState();
    return;
  }
  if (!incoming.length) {
    if (playerQuestion) speechTimer = window.setTimeout(() => { showPlayerSpeech(""); flushPendingRoomState(); }, SPEECH_BUBBLE_HOLD_MS);
    return;
  }
  let current = 0;
  speechActive = true;
  const transcript = document.querySelector<HTMLElement>("#transcript");
  const next = () => {
    if (token !== speechToken) return;
    showPlayerSpeech("");
    const message = incoming[current++];
    if (!message) {
      speechActive = false;
      showPlayerSpeech("");
      stage?.setSpeaker(null);
      displayReadingLock();
      flushPendingRoomState();
      return;
    }
    const article = document.getElementById(`message-${message.id}`);
    const body = article?.querySelector<HTMLElement>(".message-text, .stage-message-text");
    if (!article || !body) { next(); return; }
    article.classList.remove("pending-message");
    article.classList.add("speaking");
    body.textContent = "";
    const isPlayerLine = isLocalPlayerMessage(message);
    const isOtherPlayerLine = Boolean(message.player_id && !isPlayerLine);
    const sharkIndex = game?.sharks.findIndex((shark: any) => shark.name === message.speaker) ?? -1;
    const speakerFirstName = message.speaker.trim().split(/\s+/)[0] || message.speaker;
    if (isPlayerLine) stage?.setSpeaker(-1);
    else if (isOtherPlayerLine) stage?.setSpeaker(null);
    else stage?.setSpeaker(message.kind === "round" ? null : sharkIndex >= 0 ? sharkIndex + 1 : 0, "", speakerFirstName);
    announce(`${message.speaker} is speaking.`);
    transcript?.scrollTo({ top: transcript.scrollHeight, behavior: "smooth" });
    const glyphs = Array.from(message.text);
    const startedAt = performance.now();
    const type = () => {
      if (token !== speechToken) return;
      const elapsed = performance.now() - startedAt;
      const visibleCount = Math.min(glyphs.length, Math.ceil(glyphs.length * elapsed / SPEECH_BUBBLE_DURATION_MS));
      const visibleText = glyphs.slice(0, visibleCount).join("");
      body.textContent = visibleText;
      article.setAttribute("aria-label", visibleText ? `${message.speaker}: ${visibleText}` : `${message.speaker} is speaking`);
      if (isPlayerLine) showPlayerSpeech(visibleText);
      else if (isOtherPlayerLine) showPlayerSpeech("");
      else stage?.updateSpeech(visibleText);
      transcript?.scrollTo({ top: transcript.scrollHeight, behavior: "auto" });
      if (elapsed < SPEECH_BUBBLE_DURATION_MS) {
        speechTimer = window.setTimeout(type, Math.min(50, SPEECH_BUBBLE_DURATION_MS - elapsed));
        return;
      }
      body.textContent = message.text;
      article.setAttribute("aria-label", `${message.speaker}: ${message.text}`);
      article.classList.remove("speaking");
      if (isPlayerLine) showPlayerSpeech(message.text);
      else if (isOtherPlayerLine) showPlayerSpeech("");
      announce(`${message.speaker}: ${message.text}`);
      speechTimer = window.setTimeout(() => {
        if (token !== speechToken) return;
        showPlayerSpeech("");
        stage?.setSpeaker(null);
        speechTimer = window.setTimeout(next, current < incoming.length ? SPEECH_BUBBLE_GAP_MS : 0);
      }, SPEECH_BUBBLE_HOLD_MS);
    };
    type();
  };
  if (playerQuestion) speechTimer = window.setTimeout(next, 850);
  else next();
  displayReadingLock();
}

function renderLanding() {
  disconnectRoom();
  stopSpeech();
  offerEditorOpen = false;
  offerDraft = null;
  reviewingOffer = false;
  window.clearTimeout(readingTickTimer);
  readingUntil = 0;
  wasReadingLocked = false;
  game = null;
  ui.innerHTML = `
    <div class="landing-shell">
      <header class="topbar">
        <a class="brand" href="#" aria-label="Shrimp Tank home"><span class="brand-mark">ST</span><span>SHRIMP TANK<small>UNDERWRITING LAB</small></span></a>
        <div class="topbar-right"><span class="live-dot"></span><span>SIMULATION MODE</span><span class="topbar-divider"></span><span>01 / 01</span></div>
      </header>
      <section class="hero-layout">
        <div class="hero-copy">
          <p class="eyebrow"><span class="eyebrow-line"></span> CAPITAL HAS A COST</p>
          <h1>Every deal<br />has a <em>risk.</em></h1>
          <p class="hero-intro">Step into the tank. Question the founder, uncover what the pitch leaves out, then decide if the return is worth the risk.</p>
          <div class="setup-card">
            <div class="setup-heading"><span>SET YOUR SESSION</span><span class="mono muted">01 — 04 PITCHES</span></div>
            <div class="setup-options">
              <label class="field-label" for="pitch-count">PITCHES</label>
              <select id="pitch-count" class="select-control">
                <option value="4" ${selectedPitchCount === 4 ? "selected" : ""}>4 · Full session</option>
                <option value="3" ${selectedPitchCount === 3 ? "selected" : ""}>3 · Short session</option>
                <option value="2" ${selectedPitchCount === 2 ? "selected" : ""}>2 · Quick round</option>
                <option value="1" ${selectedPitchCount === 1 ? "selected" : ""}>1 · Single pitch</option>
              </select>
            </div>
            <div class="setup-options difficulty-options">
              <span class="field-label">STARTING CAPITAL</span>
              <div class="segmented" role="group" aria-label="Starting capital">
                ${["easy", "medium", "hard"].map((level) => `<button type="button" data-difficulty="${level}" class="segment ${selectedDifficulty === level ? "selected" : ""}"><span>${level}</span><small>${level === "easy" ? "$350K" : level === "medium" ? "$250K" : "$175K"}</small></button>`).join("")}
              </div>
            </div>
            <button type="button" id="start-game" class="primary-button"><span>TAKE YOUR SEAT</span><span class="button-arrow">↗</span></button>
            <button type="button" id="watch-opening" class="showcase-button"><span>WATCH STUDIO INTRO</span><span aria-hidden="true">▶</span></button>
            <p class="setup-note"><span>✳</span> Fictional scenarios · No real credit decisions</p>
          </div>
        </div>
        <div class="hero-scene" aria-hidden="true">
          <div class="scene-vignette"></div>
          <div class="hero-quote"><span class="quote-mark">“</span><p>I'm not asking you to believe in the idea. I'm asking you to look at the numbers.</p><span class="quote-credit">— A FOUNDER, SOMEWHERE IN THE TANK</span></div>
          <div class="hero-floor-label">THE DECISION IS YOURS <span>◆</span></div>
        </div>
      </section>
      <footer class="landing-footer"><span>BUILT FOR BETTER UNDERWRITING INSTINCTS</span><span>THE FIVE Cs OF CREDIT &nbsp;·&nbsp; CHARACTER / CAPACITY / CAPITAL / COLLATERAL / CONDITIONS</span></footer>
    </div>
    <div id="toast" class="toast" role="status" aria-live="polite"></div>`;
  stage?.mount(document.querySelector<HTMLElement>(".hero-scene")!);
  stage?.setPitch("");
  document.querySelector<HTMLSelectElement>("#pitch-count")!.addEventListener("change", (event) => { selectedPitchCount = Number((event.target as HTMLSelectElement).value); });
  document.querySelectorAll<HTMLButtonElement>("[data-difficulty]").forEach((button) => button.addEventListener("click", () => {
    selectedDifficulty = button.dataset.difficulty || "medium";
    document.querySelectorAll("[data-difficulty]").forEach((node) => node.classList.toggle("selected", node === button));
  }));
  document.querySelector<HTMLButtonElement>("#start-game")!.addEventListener("click", startGame);
  document.querySelector<HTMLButtonElement>("#watch-opening")!.addEventListener("click", watchOpening);
}

async function playOpeningCutscene(showcase: boolean, keepOverlayAfterComplete = false): Promise<HTMLElement | null> {
  await stageReady;
  if (!stage) return null;

  const cutscene = document.createElement("section");
  cutscene.className = "intro-cutscene";
  cutscene.setAttribute("aria-label", showcase ? "Shrimp Tank studio showcase" : "Opening cutscene");
  cutscene.innerHTML = `
    <div id="cutscene-stage" class="cutscene-stage" aria-hidden="true"></div>
    <div class="cutscene-bottomline"><button type="button" id="skip-intro" class="skip-intro">SKIP CUTSCENE <span>↗</span></button></div>
    <p class="sr-only">The presenter enters through backstage doors, walks down the hallway, and comes onto the stage.${showcase ? " The camera then sweeps across the studio before returning to the investor viewpoint." : ""}</p>`;
  ui.append(cutscene);
  stage.mount(cutscene.querySelector<HTMLElement>("#cutscene-stage")!);

  let completed = false;
  try {
    await new Promise<void>((resolve) => {
      cutscene.querySelector<HTMLButtonElement>("#skip-intro")!.addEventListener("click", () => stage?.skipIntro(), { once: true });
      stage!.intro(resolve, undefined, { showcase });
    });
    completed = true;
  } finally {
    if (!keepOverlayAfterComplete || !completed) {
      cutscene.remove();
      const heroScene = document.querySelector<HTMLElement>(".hero-scene");
      if (heroScene) stage.mount(heroScene);
    }
  }
  return keepOverlayAfterComplete ? cutscene : null;
}

async function watchOpening() {
  if (busy) return;
  busy = true;
  const button = document.querySelector<HTMLButtonElement>("#watch-opening");
  if (button) {
    button.disabled = true;
    button.innerHTML = "<span>PLAYING STUDIO INTRO…</span><span aria-hidden=\"true\">▶</span>";
  }
  try {
    await playOpeningCutscene(true);
  } catch (error) {
    toast(error instanceof Error ? error.message : "Couldn't play the studio intro.");
  } finally {
    busy = false;
    if (button?.isConnected) {
      button.disabled = false;
      button.innerHTML = "<span>WATCH STUDIO INTRO</span><span aria-hidden=\"true\">▶</span>";
    }
  }
}

async function startGame() {
  if (busy) return;
  offerEditorOpen = false;
  offerDraft = null;
  const button = document.querySelector<HTMLButtonElement>("#start-game") || document.querySelector<HTMLButtonElement>("#play-again");
  busy = true;
  if (button) { button.disabled = true; button.innerHTML = "<span>PREPARING THE TANK…</span><span class=\"spinner\"></span>"; }
  let transitionCover: HTMLElement | null = null;
  try {
    transitionCover = await playOpeningCutscene(false, true);
    if (button) button.innerHTML = "<span>SETTING THE TABLE…</span><span class=\"spinner\"></span>";
    game = personalizeGameState(await api<GameState>("/api/sessions", { method: "POST", body: JSON.stringify({ total_pitches: selectedPitchCount, difficulty: selectedDifficulty }) }));
    localStorage.setItem("credit-tank-session", game.id);
    history.replaceState(null, "", `${location.pathname}${location.search}`);
    holdForDialogue(game.messages);
    stage?.setPitch(game.pitch.archetype, game.pitch.company);
    busy = false;
    renderGame(game.messages);
    transitionCover?.remove();
  } catch (error) {
    transitionCover?.remove();
    busy = false;
    renderLanding();
    toast(error instanceof Error ? error.message : "Couldn't start the session.");
  }
}

function displayReadingLock() {
  window.clearTimeout(readingTickTimer);
  const controls = document.querySelectorAll<HTMLInputElement | HTMLButtonElement | HTMLSelectElement>(".turn-control");
  const label = document.querySelector<HTMLElement>("#reading-label");
  const reveal = document.querySelector<HTMLButtonElement>("#reveal-decision");
  const tick = () => {
    const remaining = Math.max(0, readingUntil - Date.now());
    const conversationLocked = Boolean(speechActive && game?.question_asked && game.phase === "investigate");
    const waitingForTurn = Boolean(game && game.phase === "investigate" && (!game.is_my_turn || game.human_out));
    const locked = remaining > 0 || conversationLocked || waitingForTurn;
    controls.forEach((control) => {
      const ownDisabled = control.dataset.intrinsicDisabled === "true";
      control.disabled = busy || ownDisabled || remaining > 0 || conversationLocked || waitingForTurn;
    });
    if (label) label.textContent = busy && reviewingOffer
      ? "FOUNDER REVIEWING YOUR OFFER"
      : waitingForTurn
      ? game?.human_out ? "YOU'RE OUT · WATCH THE TABLE" : `WAITING FOR ${game?.current_player_name?.toUpperCase() ?? "YOUR TURN"}`
      : remaining > 0 ? `READ THE ROOM · ${Math.ceil(remaining / 1000)}s` : conversationLocked ? "HEAR THE FULL TABLE" : "YOUR MOVE";
    if (reveal) {
      const readyToReveal = remaining <= 0 && !speechActive;
      reveal.textContent = game?.immediate_acceptance
        ? readyToReveal ? "CONTINUE TO DEAL DETAILS ↗" : "SHOW TRANSCRIPT & DEAL DETAILS ↗"
        : readyToReveal ? "REVEAL FOUNDER'S DECISION ↗" : "SHOW TRANSCRIPT & REVEAL DECISION ↗";
    }
    if (wasReadingLocked && !locked) announce(game?.question_asked ? "The conversation is complete. You may submit an offer or pass." : "Your move. You may ask a question or make an offer.");
    wasReadingLocked = locked;
    if (remaining > 0) readingTickTimer = window.setTimeout(tick, Math.min(1000, remaining));
  };
  tick();
}

function readOfferDraft(): OfferDraft | null {
  if (!game) return null;
  return {
    amount: Number(document.querySelector<HTMLInputElement>("#offer-amount")?.value ?? game.pitch.ask_amount),
    rate: Number(document.querySelector<HTMLInputElement>("#offer-rate")?.value ?? game.pitch.opening_rate),
    royalty: Number(document.querySelector<HTMLInputElement>("#offer-royalty")?.value ?? 0),
    termMonths: Number(document.querySelector<HTMLSelectElement>("#offer-term")?.value ?? 36),
    secured: Boolean(document.querySelector<HTMLInputElement>("#offer-secured")?.checked),
  };
}

function renderGame(animateMessages: Message[] = []) {
  stopSpeech();
  if (!game) return;
  connectRoom(game.id);
  stage?.setPitch(game.pitch.archetype, game.pitch.company);
  if (game.phase === "complete") { renderScorecard(); return; }
  if (game.phase === "pitch_result") { renderPitchResult(); return; }
  const incomingIds = new Set(reducedMotion.matches ? [] : animateMessages.filter((message) => message.kind !== "question").map((message) => message.id));
  const aiBadge = game.ai_mode === "offline" ? "GROK KEY NEEDED" : "GROK LIVE DIALOGUE";
  const messages = game.messages.map((message) => {
    const investor = game!.sharks.find((shark: any) => shark.name === message.speaker);
    const speakerLabel = investor ? `${message.speaker} (${investor.title})` : message.speaker;
    const isOwnPlayerMessage = message.player_id ? message.player_id === game!.self_player_id : message.speaker === "You";
    const tone = isOwnPlayerMessage ? "from-you" : message.player_id ? "from-player" : message.speaker === "You" || message.kind === "question" || message.kind === "pass" ? "from-you" : message.kind === "shark_question" || message.kind === "offer" || message.kind === "reply" ? "from-shark" : message.kind === "round" ? "stage-message" : message.kind === "counter" ? "from-founder counter" : "from-founder";
    return `
    <article id="message-${esc(message.id)}" role="group" aria-label="${esc(`${speakerLabel}: ${message.text}`)}" class="message ${tone} ${incomingIds.has(message.id) ? "pending-message" : ""}">
      ${message.kind === "round" ? `<p class="stage-message-text">${incomingIds.has(message.id) ? "" : esc(message.text)}</p>` : `<div class="message-meta"><span class="speaker">${esc(message.speaker)}</span>${investor ? `<span class="speaker-personality">(${esc(investor.title)})</span>` : ""}</div><p class="message-text">${incomingIds.has(message.id) ? "" : esc(message.text)}</p>`}
    </article>`;
  }).join("");
  const disclosures = game.disclosures.length ? game.disclosures.map((key: string) => `<span class="clue-chip found">${esc(key)}</span>`).join("") : `<span class="clue-empty">Nothing surfaced yet.</span>`;
  const offerRows = game.offers.length ? game.offers.map((offer: any) => `
    <div class="offer-row"><div><span class="offer-name">${esc(offer.investor)}</span><small>${offer.secured ? "SECURED" : "UNSECURED"} · ${offer.term_months} MO</small></div><div class="offer-numbers"><b>${money(offer.amount)}</b><small>${Number(offer.rate).toFixed(1)}% APR${offer.royalty ? ` · ${offer.royalty}% REV` : ""}</small></div></div>`).join("") : `<div class="empty-offers"><span class="empty-offer-icon">↗</span><span>No active offers</span><small>The table is still open.</small></div>`;
  const portfolioCards = (game.investor_portfolios ?? []).map((portfolio: any) => {
    const recommendation = portfolio.recommendation ?? {};
    const marketAvailable = portfolio.market_mode === "coinbase_live";
    const marketLabel = marketAvailable ? "PAPER TRADE SIGNAL" : portfolio.market_mode === "partial" ? "PARTIAL DATA · HOLD" : "MARKET FEED UNAVAILABLE";
    const paperAmount = Number(recommendation.amount_usd ?? 0) > 0 ? ` · ${money(recommendation.amount_usd)} PAPER` : "";
    const holdings = (portfolio.positions ?? []).map((position: any) => `<div class="portfolio-holding"><span>${esc(position.asset)}</span><b>${money(position.market_value_usd)}</b><small>${position.change_24h_pct == null ? "NO QUOTE" : `${Number(position.change_24h_pct) >= 0 ? "+" : ""}${Number(position.change_24h_pct).toFixed(1)}% · 24H`}</small></div>`).join("");
    return `<article class="portfolio-card"><div class="portfolio-card-heading"><div><h3>${esc(portfolio.investor)}</h3><span>${esc(portfolio.strategy)}</span></div><span class="portfolio-return ${Number(portfolio.return_pct) < 0 ? "negative" : ""}">${Number(portfolio.return_pct) >= 0 ? "+" : ""}${Number(portfolio.return_pct ?? 0).toFixed(1)}%</span></div><div class="portfolio-metrics"><div><span>PAPER NAV</span><b>${money(portfolio.total_value_usd)}</b></div><div><span>CASH</span><b>${money(portfolio.cash_usd)}</b></div></div><div class="portfolio-holdings">${holdings}</div><div class="portfolio-signal"><span class="portfolio-signal-label">${esc(marketLabel)}</span><b>${esc(String(recommendation.action ?? "hold").replace("trim", "trim / sell").toUpperCase())}${recommendation.asset ? ` · ${esc(recommendation.asset)}` : ""}${esc(paperAmount)}</b><p>${esc(recommendation.summary ?? "No portfolio recommendation is available.")}</p></div></article>`;
  }).join("");
  const portfolioDesk = portfolioCards ? `<details class="portfolio-desk"><summary><span class="portfolio-summary-title"><span class="portfolio-chevron" aria-hidden="true">›</span>INVESTOR PAPER PORTFOLIOS</span><small>SIMULATED · COINBASE PUBLIC CANDLES</small></summary><div class="portfolio-grid">${portfolioCards}</div><p class="portfolio-disclaimer">Illustrative crypto portfolios and rule-based signals. No Coinbase account, wallet, funds, or real trades are connected.</p></details>` : "";
  const capitalPercent = game.starting_capital > 0 ? Math.min(100, Math.max(0, game.balance / game.starting_capital * 100)) : 0;
  const isMyTurn = game.is_my_turn ?? true;
  const canAct = isMyTurn && !game.human_out;
  const decisionRequired = canAct && game.question_asked && game.phase === "investigate";
  const questionInvitation = canAct && !game.question_asked && game.phase === "investigate" && !busy;
  const pitchReview = game.phase === "pitch_review";
  const immediateAcceptance = Boolean(game.immediate_acceptance);
  const offerTerms = offerDraft ?? { amount: game.pitch.ask_amount, rate: Number(game.pitch.opening_rate), royalty: 0, termMonths: 36, secured: false };
  const moveHeading = busy && reviewingOffer ? "FOUNDER REVIEWING YOUR OFFER" : pitchReview ? immediateAcceptance ? "DEAL ACCEPTED" : "PITCH REVIEW" : offerEditorOpen ? "SET OFFER TERMS" : "MAKE YOUR MOVE";
  const stallWarning = game.quiet_rounds >= game.quiet_round_limit - 1
    ? " No new offer this round ends the pitch. The founder can accept a qualifying offer or walk away."
    : "";
  const moveSubtitle = busy && reviewingOffer
    ? "The founder is considering your terms. Their reply comes before the investor discussion."
    : pitchReview
    ? immediateAcceptance
      ? "The founder accepted the offer matching their request. The conversation remains available to review."
      : "The founder's decision is intentionally held until the full conversation has been reviewed."
    : !canAct
      ? game.human_out ? "You are out on this pitch. Watch the remaining investors negotiate." : `${game.current_player_name ?? "Another investor"} has the floor. Your turn begins after their move.`
    : offerEditorOpen
      ? `Fund at least ${money(game.pitch.ask_amount)} at ${Number(game.pitch.opening_rate).toFixed(1)}% or less with no revenue share for immediate acceptance.`
      : `Choose how you want to respond to this pitch.${stallWarning}`;
  const reviewHeading = immediateAcceptance ? "DEAL ACCEPTED · PITCH CLOSED" : "ROUND CLOSED · CONVERSATION PRESERVED";
  const reviewText = immediateAcceptance
    ? "The matching offer is accepted. Review the conversation or continue to the deal details."
    : "All messages and offers remain above. Reveal the founder's decision when you are ready, or reveal the full transcript and decision now.";
  const reviewAction = immediateAcceptance ? "CONTINUE TO DEAL DETAILS ↗" : "SHOW TRANSCRIPT & REVEAL DECISION ↗";
  const moveContent = pitchReview
    ? `<div class="decision-review" role="status"><span class="round-required-mark">✓</span><div><b>${reviewHeading}</b><p>${reviewText}</p></div><button type="button" id="reveal-decision" class="primary-button">${reviewAction}</button></div>`
    : !canAct
      ? `<div class="turn-waiting" role="status"><span class="turn-waiting-mark" aria-hidden="true">${game.human_out ? "✓" : "…"}</span><b>${game.human_out ? "YOU'RE OUT · CONVERSATION CONTINUES" : `WAITING FOR ${esc(game.current_player_name ?? "THE OTHER INVESTOR")}`}</b><span>${game.human_out ? "You can still follow the shared conversation and offers." : "The shared pitch advances when the active investor finishes their turn."}</span></div>`
    : offerEditorOpen
      ? `<form id="offer-form" class="offer-form offer-terms-form">
          <label><span>LOAN AMOUNT</span><div class="money-input"><i>$</i><input id="offer-amount" class="turn-control" type="number" min="25000" max="750000" step="5000" value="${offerTerms.amount}" required /></div></label>
          <label><span>ANNUAL INTEREST</span><div class="number-input"><input id="offer-rate" class="turn-control" type="number" min="0" max="40" step="0.25" value="${offerTerms.rate.toFixed(2)}" required /><i>%</i></div></label>
          <label><span>REVENUE SHARE</span><div class="number-input"><input id="offer-royalty" class="turn-control" type="number" min="0" max="12" step="0.25" value="${offerTerms.royalty}" /><i>%</i></div></label>
          <label><span>TERM</span><select id="offer-term" class="select-control turn-control"><option value="24" ${offerTerms.termMonths === 24 ? "selected" : ""}>24 months</option><option value="36" ${offerTerms.termMonths === 36 ? "selected" : ""}>36 months</option><option value="48" ${offerTerms.termMonths === 48 ? "selected" : ""}>48 months</option><option value="60" ${offerTerms.termMonths === 60 ? "selected" : ""}>60 months</option></select></label>
          <label class="secured-control"><input id="offer-secured" class="turn-control" type="checkbox" ${offerTerms.secured ? "checked" : ""} /><span>SECURED</span></label>
          <button type="button" id="back-to-moves" class="text-button back-button turn-control">← BACK</button>
          <button type="submit" class="primary-button offer-submit turn-control" data-intrinsic-disabled="${game.human_out}" ${game.human_out || busy || !canAct ? "disabled" : ""}>SUBMIT OFFER <span>↗</span></button>
        </form><div class="dock-footnote">Interest and revenue share are simulated terms. This game does not issue a loan.</div>`
      : `<div class="move-choice-grid" role="group" aria-label="Choose your move">
          <button type="button" id="choose-offer" class="primary-button move-choice-button turn-control" data-intrinsic-disabled="${game.human_out}" ${game.human_out || busy || !canAct ? "disabled" : ""}>SUBMIT OFFER <span class="button-arrow">↗</span></button>
          <button type="button" id="pass-turn" class="text-button move-choice-button turn-control" ${busy || !canAct ? "disabled" : ""}>PASS</button>
          <button type="button" id="out-turn" class="text-button out-button move-choice-button turn-control" aria-label="Leave the pitch while the conversation continues among the remaining investors" data-intrinsic-disabled="${game.human_out}" ${game.human_out || busy || !canAct ? "disabled" : ""}>I'M OUT - CONVERSATION CONTINUES</button>
        </div>`;
  const localPlayerName = game.players?.find((player) => player.id === game?.self_player_id)?.name ?? "PLAYER";
  const isHost = Boolean(game.players?.find((player) => player.id === game?.self_player_id)?.is_host);
  const resetControl = isHost ? `<button type="button" id="debug-reset" class="debug-reset-button" aria-label="Reset game and return to setup" title="Reset game and return to setup"><span class="debug-reset-label">RESET GAME</span><span aria-hidden="true">↻</span></button>` : "";
  const turnSubtitle = canAct
    ? game.question_asked ? "YOUR TURN · Choose an offer, pass, or leave." : "YOUR TURN · Ask a question or choose a move."
    : game.human_out ? "You are out · Follow the table's shared conversation." : `Waiting for ${game.current_player_name ?? "another investor"} · Your turn follows.`;
  const composeContent = decisionRequired
    ? `<div class="round-locked"><span class="round-required-mark">!</span><div><b>YOUR QUESTION HAS BEEN USED</b><p>This round ends with a decision. Use the highlighted decision bar below to submit an offer, pass, or leave.</p></div><a href="#offer-dock" class="decision-banner-action">GO TO DECISION ↓</a></div>`
    : pitchReview ? ""
      : !canAct
        ? `<div class="turn-waiting compose-waiting" role="status"><b>${game.human_out ? "YOU'RE OUT · CONVERSATION CONTINUES" : `WAITING FOR ${esc(game.current_player_name ?? "THE OTHER INVESTOR")}`}</b><span>${game.human_out ? "The room's pitch and offers remain visible to you." : "Question and move controls unlock when it is your turn."}</span></div>`
        : `<div class="prompt-row"><span>ASK ABOUT</span><button type="button" class="prompt-chip" data-question="What's your personal credit history and current debt?">Credit</button><button type="button" class="prompt-chip" data-question="How much free cash flow do you have after paying suppliers and debt?">Capacity</button><button type="button" class="prompt-chip" data-question="How much have you invested in the business?">Capital</button><button type="button" class="prompt-chip" data-question="What assets could you pledge as collateral?">Collateral</button><button type="button" class="prompt-chip" data-question="Who are your largest customers, and how secure are those orders?">Customers</button></div><form id="question-form" class="question-form ${questionInvitation ? "question-invitation" : ""}"><label class="sr-only" for="question-input">Question for the founder</label><input id="question-input" class="turn-control" data-intrinsic-disabled="false" type="text" maxlength="400" placeholder="Ask your own question…" autocomplete="off" ${busy ? "disabled" : ""} /><button class="send-button turn-control" data-intrinsic-disabled="false" type="submit" aria-label="Ask question" ${busy ? "disabled" : ""}>↗</button></form><div class="turn-bar"><span id="reading-label">YOUR MOVE</span><span>MAX 400 CHARACTERS</span></div>`;

  ui.innerHTML = `
    <div class="game-shell has-full-scene">
      <div id="game-stage" class="game-stage" aria-hidden="true"></div>
      <div id="player-speech-bubble" class="player-speech-bubble" hidden><p></p></div>
      <a class="skip-link" href="#conversation-panel">Skip to the conversation</a>
      <header class="game-topbar">
        <a class="brand compact" href="#"><span class="brand-mark">ST</span><span>SHRIMP TANK<small>UNDERWRITING LAB</small></span></a>
        <div class="session-progress"><div class="progress-label"><span>SESSION PROGRESS</span><b>${String(game.pitch_index).padStart(2, "0")} <i>/</i> ${String(game.total_pitches).padStart(2, "0")}</b></div><div class="progress-track"><span style="width:${game.pitch_index / game.total_pitches * 100}%"></span></div></div>
        <div class="game-status"><span class="live-dot"></span><span>${aiBadge}</span></div>
        <div class="room-tools"><span id="room-presence" class="room-presence" role="status">CONNECTING…</span><button type="button" id="invite-room" class="invite-room-button" aria-label="Copy an invite link for this shared game" title="Copy an invite link for this shared game">INVITE</button></div>
        ${resetControl}
        <button type="button" class="icon-button exit-button" id="exit-game" aria-label="Exit session">×</button>
      </header>
      <section class="game-grid">
        <aside class="side-column left-column">
          <div class="panel company-panel"><div class="panel-label"><span>THE ASK</span><span class="panel-index">01</span></div><h2 class="company-name">${esc(game.pitch.company)}</h2><div class="ask-value">${money(game.pitch.ask_amount)}</div><div class="ask-purpose">${esc(game.pitch.purpose)}</div><div class="mini-metric"><span>REPORTED ANNUAL REVENUE</span><b>${money(game.pitch.public_revenue)}</b></div><div class="mini-metric"><span>PROPOSED OPENING RATE</span><b>${Number(game.pitch.opening_rate).toFixed(1)}<small>% APR</small></b></div></div>
          <div class="panel ledger-panel"><div class="panel-label"><span>ACTIVE OFFERS</span><span class="panel-index">${String(game.offers.length).padStart(2, "0")}</span></div><div class="offer-list">${offerRows}</div></div>
          <div class="panel capital-panel"><div class="panel-label"><span>YOUR AVAILABLE CAPITAL</span><b class="capital-percent">${Math.round(capitalPercent)}%</b></div><div class="capital-track" role="progressbar" aria-label="Available starting capital" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${Math.round(capitalPercent)}" aria-valuetext="${money(game.balance)} remaining from ${money(game.starting_capital)}"><span style="width:${capitalPercent}%"></span></div><div class="capital-values"><div><span>CASH LEFT</span><b>${money(game.balance)}</b></div><div><span>STARTED WITH</span><b>${money(game.starting_capital)}</b></div></div></div>
          <div class="panel discovery-panel"><div class="panel-label"><span>WHAT YOU'VE UNCOVERED</span><span class="panel-index">${String(game.disclosures.length).padStart(2, "0")}</span></div><div class="clue-list">${disclosures}</div></div>
        </aside>
        <section id="conversation-panel" class="panel dialogue-panel" aria-label="Pitch dialogue" tabindex="-1">
          <div class="dialogue-top"><div class="panel-label dialogue-topline"><span>THE CONVERSATION</span></div><div class="conversation-round" role="status" aria-label="Round ${game.round}"><span>ROUND</span><b>${String(game.round).padStart(2, "0")}</b></div><div class="conversation-subtitle"><span>${esc(turnSubtitle)}</span><span class="player-seat-label">${esc(localPlayerName)}${isHost ? " · HOST" : ""}</span></div></div>
          ${portfolioDesk}
          <p class="sr-only">A full-screen, low-poly television pitch studio sits behind the game interface. Drag any exposed area of the scene to look around; the interface remains in place.</p>
          <div class="transcript" id="transcript">${messages}<div class="transcript-end" id="transcript-end"></div></div>
          <div class="compose-area" ${pitchReview ? "hidden" : ""}>
            ${composeContent}
          </div>
        </section>
      </section>
      <section id="offer-dock" class="offer-dock ${decisionRequired ? "round-required" : ""} ${pitchReview ? "review-dock" : ""}">
        <div class="dock-heading"><div><span class="panel-label">${moveHeading}</span><span class="dock-subtitle">${moveSubtitle}</span></div></div>
        ${moveContent}
      </section>
      <footer class="game-footer"><span>FICTIONAL BUSINESS CASE · CRS DATA IS SYNTHETIC SANDBOX DATA</span><span>NO REAL CREDIT DECISIONS · FIVE Cs TEACHING RUBRIC</span></footer>
    </div>
    <div id="toast" class="toast" role="status" aria-live="polite"></div>`;

  stage?.mount(document.querySelector<HTMLElement>("#game-stage")!);
  const transcript = document.querySelector<HTMLElement>("#transcript")!;
  transcript.scrollTop = transcript.scrollHeight;
  document.querySelectorAll<HTMLButtonElement>(".prompt-chip").forEach((button) => button.addEventListener("click", () => {
    const input = document.querySelector<HTMLInputElement>("#question-input");
    if (input && !game?.question_asked) { input.value = button.dataset.question || ""; input.focus(); }
  }));
  document.querySelector<HTMLFormElement>("#question-form")?.addEventListener("submit", askFounder);
  const offerForm = document.querySelector<HTMLFormElement>("#offer-form");
  const saveOfferDraft = () => { offerDraft = readOfferDraft(); };
  offerForm?.addEventListener("input", saveOfferDraft);
  offerForm?.addEventListener("change", saveOfferDraft);
  offerForm?.addEventListener("submit", (event) => { event.preventDefault(); saveOfferDraft(); submitMove("offer"); });
  document.querySelector<HTMLButtonElement>("#choose-offer")?.addEventListener("click", () => {
    offerEditorOpen = true;
    renderGame();
    document.querySelector<HTMLInputElement>("#offer-amount")?.focus({ preventScroll: true });
  });
  document.querySelector<HTMLButtonElement>("#back-to-moves")?.addEventListener("click", () => {
    offerDraft = readOfferDraft();
    offerEditorOpen = false;
    renderGame();
    document.querySelector<HTMLButtonElement>("#choose-offer")?.focus({ preventScroll: true });
  });
  document.querySelector<HTMLButtonElement>("#pass-turn")?.addEventListener("click", () => submitMove("pass"));
  document.querySelector<HTMLButtonElement>("#out-turn")?.addEventListener("click", () => submitMove("out"));
  document.querySelector<HTMLButtonElement>("#reveal-decision")?.addEventListener("click", revealDecision);
  document.querySelector<HTMLButtonElement>("#debug-reset")?.addEventListener("click", resetGameToMenu);
  document.querySelector<HTMLButtonElement>("#invite-room")!.addEventListener("click", inviteToRoom);
  document.querySelector<HTMLButtonElement>("#exit-game")!.addEventListener("click", () => {
    if (window.confirm("Leave this session? Its in-memory state is available until the game server restarts.")) { localStorage.removeItem("credit-tank-session"); renderLanding(); }
  });
  displayReadingLock();
  playDialogue(animateMessages);
}

function resetGameToMenu() {
  if (!game || busy) return;
  const sessionId = game.id;
  localStorage.removeItem("credit-tank-session");
  renderLanding();
  void api(`/api/sessions/${encodeURIComponent(sessionId)}`, { method: "DELETE" }).catch(() => undefined);
}

async function askFounder(event: SubmitEvent) {
  event.preventDefault();
  if (!game || busy || !game.is_my_turn || game.human_out || game.question_asked || Date.now() < readingUntil) return;
  const input = document.querySelector<HTMLInputElement>("#question-input")!;
  const question = input.value.trim();
  if (question.length < 2) { toast("Write a question or choose one of the prompts."); return; }
  busy = true;
  renderGame();
  const priorCount = game.messages.length;
  const transcript = document.querySelector<HTMLElement>("#transcript");
  const makeQuestionMessage = () => {
    const playerName = game?.players?.find((player) => player.id === game?.self_player_id)?.name ?? "You";
    const article = document.createElement("article");
    article.className = "message from-you";
    article.setAttribute("role", "group");
    article.setAttribute("aria-label", `${playerName}: ${question}`);
    const meta = document.createElement("div");
    meta.className = "message-meta";
    const speaker = document.createElement("span");
    speaker.className = "speaker";
    speaker.textContent = playerName;
    const body = document.createElement("p");
    body.className = "message-text";
    body.textContent = question;
    meta.append(speaker);
    article.append(meta, body);
    transcript?.append(article);
    transcript?.scrollTo({ top: transcript.scrollHeight, behavior: "smooth" });
    return article;
  };
  makeQuestionMessage();
  const progress = document.createElement("div");
  progress.className = "stream-status";
  progress.id = "stream-status";
  progress.setAttribute("role", "status");
  progress.setAttribute("aria-live", "polite");
  progress.innerHTML = '<span class="stream-spinner" aria-hidden="true"></span><span>The founder and investors are preparing their responses…</span>';
  transcript?.append(progress);
  showPlayerSpeech(question);
  stage?.setSpeaker(-1);
  try {
    const sessionId = game.id;
    game = personalizeGameState(await streamQuestion(sessionId, question, (message) => {
      if (message.field === "player_question") return;
      const statusText = progress.querySelector<HTMLElement>("span:last-child");
      if (statusText) statusText.textContent = message.field === "shark_question"
        ? `${message.speaker} is asking a follow-up…`
        : message.field === "shark_reaction"
          ? `${message.speaker} is weighing in…`
          : `${message.speaker} is responding…`;
      transcript?.scrollTo({ top: transcript.scrollHeight, behavior: "smooth" });
    }, () => {
      // Keep the status current while the completed exchange is being assembled.
    }, (message) => {
      const statusText = progress.querySelector<HTMLElement>("span:last-child");
      if (statusText) statusText.textContent = message;
    }));
    progress.remove();
    const fresh = game.messages.slice(priorCount);
    // Render the server's saved messages and stage the transcript with the 3D bubbles.
    // Decision controls remain locked until this dialogue playback finishes.
    readingUntil = 0;
    busy = false;
    renderGame(fresh);
    announce("Your question was recorded. This round must now conclude with an offer, pass, or exit.");
  } catch (error) {
    busy = false;
    renderGame();
    toast(error instanceof Error ? error.message : "The founder couldn't answer.");
  } finally { busy = false; flushPendingRoomState(); }
}

async function submitMove(action: "offer" | "pass" | "out") {
  if (!game || busy || !game.is_my_turn || game.human_out || Date.now() < readingUntil || (speechActive && game.question_asked && game.phase === "investigate")) return;
  busy = true;
  const previousMessages = game.messages.length;
  const payload: any = { action };
  if (action === "offer") {
    const terms = readOfferDraft();
    if (!terms) { busy = false; return; }
    offerDraft = terms;
    payload.amount = terms.amount;
    payload.rate = terms.rate;
    payload.royalty = terms.royalty;
    payload.term_months = terms.termMonths;
    payload.secured = terms.secured;
  }
  reviewingOffer = action === "offer";
  if (reviewingOffer) announce("Your offer has been submitted. The founder is considering the terms.");
  renderGame();
  try {
    game = personalizeGameState(await api<GameState>(`/api/sessions/${game.id}/decision`, { method: "POST", body: JSON.stringify(payload) }));
    reviewingOffer = false;
    const fresh = game.messages.slice(previousMessages);
    if (game.phase === "investigate" || game.phase === "pitch_review") holdForDialogue(fresh);
    else readingUntil = 0;
    offerEditorOpen = false;
    offerDraft = null;
    busy = false;
    renderGame(fresh);
    if (game.phase === "pitch_review") announce(game.immediate_acceptance
      ? "The founder accepted the matching offer. The pitch is closed."
      : "The round is closed. Review the complete conversation before revealing the founder's decision.");
  } catch (error) {
    reviewingOffer = false;
    busy = false;
    renderGame();
    toast(error instanceof Error ? error.message : "Couldn't submit that move.");
  } finally { busy = false; flushPendingRoomState(); }
}

async function revealDecision() {
  if (!game || busy || game.phase !== "pitch_review") return;
  if (Date.now() < readingUntil || speechActive) showFullTranscript();
  busy = true;
  const button = document.querySelector<HTMLButtonElement>("#reveal-decision");
  if (button) { button.disabled = true; button.textContent = "REVEALING DECISION…"; }
  try {
    game = personalizeGameState(await api<GameState>(`/api/sessions/${game.id}/reveal`, { method: "POST", body: "{}" }));
    readingUntil = 0;
    renderPitchResult();
    announce("The founder's decision is now revealed.");
  } catch (error) {
    busy = false;
    renderGame();
    toast(error instanceof Error ? error.message : "Couldn't reveal the founder's decision.");
  } finally { busy = false; flushPendingRoomState(); }
}

function renderPitchResult() {
  if (!game) return;
  stopSpeech();
  window.clearTimeout(readingTickTimer);
  readingUntil = 0;
  wasReadingLocked = false;
  stage?.mount(document.querySelector<HTMLElement>("#stage")!);
  const result = game.result;
  const accepted = result?.outcome === "deal";
  ui.innerHTML = `
    <div class="result-shell"><header class="game-topbar"><a class="brand compact" href="#"><span class="brand-mark">ST</span><span>SHRIMP TANK<small>UNDERWRITING LAB</small></span></a><div class="session-progress"><div class="progress-label"><span>PITCH RESOLVED</span><b>${String(game.pitch_index).padStart(2, "0")} <i>/</i> ${String(game.total_pitches).padStart(2, "0")}</b></div><div class="progress-track"><span style="width:${game.pitch_index / game.total_pitches * 100}%"></span></div></div><div class="capital-pill"><span>AVAILABLE CAPITAL</span><b>${money(game.balance)}</b></div></header>
    <section class="result-card"><div class="result-symbol ${accepted ? "accepted" : "passed"}">${accepted ? "✓" : "—"}</div><h1>${accepted ? "Deal closed." : "No deal."}</h1><p class="result-company">${esc(game.pitch.company)} <span>·</span> ${esc(game.pitch.archetype)}</p><div class="result-terms"><span>${esc(result.message)}</span></div><div class="result-actions"><button type="button" id="advance" class="primary-button">${game.pitch_index < game.total_pitches ? "NEXT PITCH" : "VIEW SCORECARD"}<span class="button-arrow">↗</span></button></div></section><footer class="game-footer"><span>FICTIONAL BUSINESS CASE</span><span>NO REAL CREDIT DECISIONS</span></footer></div><div id="toast" class="toast" role="status" aria-live="polite"></div>`;
  document.querySelector<HTMLButtonElement>("#advance")!.addEventListener("click", advance);
}

async function advance() {
  if (!game || busy) return;
  busy = true;
  if (game.pitch_index >= game.total_pitches) {
    try { game = personalizeGameState(await api<GameState>(`/api/sessions/${game.id}`)); renderScorecard(); }
    catch (error) { toast(error instanceof Error ? error.message : "Couldn't load scorecard."); }
    finally { busy = false; flushPendingRoomState(); }
    return;
  }
  try {
    game = personalizeGameState(await api<GameState>(`/api/sessions/${game.id}/next`, { method: "POST", body: "{}" }));
    offerEditorOpen = false;
    offerDraft = null;
    stage?.setPitch(game.pitch.archetype, game.pitch.company);
    holdForDialogue(game.messages);
    busy = false;
    renderGame(game.messages);
  } catch (error) { toast(error instanceof Error ? error.message : "Couldn't start the next pitch."); }
  finally { busy = false; flushPendingRoomState(); }
}

function renderScorecard() {
  if (!game?.scorecard) return;
  stopSpeech();
  window.clearTimeout(readingTickTimer);
  readingUntil = 0;
  wasReadingLocked = false;
  stage?.mount(document.querySelector<HTMLElement>("#stage")!);
  const scorecard = game.scorecard;
  const selfPlayerId = game.self_player_id;
  const rows = scorecard.pitches.map((pitch: any) => `
    <article class="score-pitch"><div class="score-pitch-head"><div><span class="eyebrow-small">${esc(pitch.archetype)} · GRADE ${pitch.grade}</span><h3>${esc(pitch.company)}</h3></div><span class="risk-tag grade-${pitch.grade}">${esc(pitch.risk_label)}</span></div><div class="five-cs">${Object.entries(pitch.assessment.components).map(([key, value]) => `<div class="cs-row"><span>${esc(key)}</span><div class="cs-track"><i style="width:${Number(value)}%"></i></div><b>${value}</b></div>`).join("")}</div><div class="score-pitch-details"><div><small>YOUR DECISION</small><b>${pitch.winner === selfPlayerId ? `FUNDED · ${money(pitch.player_offer?.amount || 0)} @ ${Number(pitch.player_offer?.rate || 0).toFixed(1)}%` : pitch.winner ? `${esc(pitch.winner_name ?? "OTHER INVESTOR").toUpperCase()} · ${esc(pitch.decision.replace("_", " ").toUpperCase())}` : "NO DEAL"}</b></div><div><small>RULES-BASED BENCHMARK</small><b>${pitch.benchmark.action === "walk_away" ? "WALK AWAY" : `${money(pitch.benchmark.amount)} @ ${Number(pitch.benchmark.rate).toFixed(1)}%`}</b></div><div><small>EXPECTED GAME P&L</small><b class="${pitch.expected_profit >= 0 ? "positive" : "negative"}">${pitch.expected_profit >= 0 ? "+" : "−"}${money(Math.abs(pitch.expected_profit))}</b></div></div><p class="score-feedback">${esc(pitch.feedback)}</p><details class="evidence-details"><summary>Reveal the founder's fictional profile</summary><div class="evidence-grid"><span>Credit score <b>${pitch.credit_score ?? "No score"}</b></span><span>Derogatory signals <b>${pitch.derogatory_count}</b></span><span>Free cash flow <b>${money(pitch.monthly_free_cash_flow)}/mo</b></span><span>Owner equity <b>${money(pitch.owner_equity)}</b></span><span>Collateral <b>${money(pitch.collateral)}</b></span><span>DSCR <b>${pitch.assessment.dscr}×</b></span></div><p>${esc(pitch.benchmark.reason)}</p></details></article>`).join("");
  ui.innerHTML = `
    <div class="scorecard-shell"><header class="game-topbar"><a class="brand compact" href="#"><span class="brand-mark">ST</span><span>SHRIMP TANK<small>UNDERWRITING LAB</small></span></a><div class="session-progress"><div class="progress-label"><span>SESSION COMPLETE</span><b>${String(game.total_pitches).padStart(2, "0")} <i>/</i> ${String(game.total_pitches).padStart(2, "0")}</b></div><div class="progress-track"><span style="width:100%"></span></div></div><div class="capital-pill"><span>PROJECTED CAPITAL</span><b>${money(scorecard.projected_ending_capital)}</b></div><div class="game-status"><span class="live-dot"></span><span>FINAL REVIEW</span></div></header>
    <section class="score-hero"><div class="score-title"><p class="eyebrow"><span class="eyebrow-line"></span>SESSION DEBRIEF</p><h1>Read the risk.<br /><em>Price the return.</em></h1><p>Your decisions, measured against a transparent teaching benchmark built around the five Cs of credit.</p></div><div class="score-circle"><span>UNDERWRITING<br />INSTINCT</span><b>${scorecard.overall_score}</b><small>OUT OF 100</small></div></section>
    <section class="score-summary"><div><span>DECISION FIT</span><b>${scorecard.decision_accuracy}<small> / 100</small></b></div><div><span>DEALS YOU FUNDED</span><b>${scorecard.deals_funded}<small> / ${scorecard.pitches.length}</small></b></div><div><span>EXPECTED GAME P&L</span><b class="${scorecard.expected_profit >= 0 ? "positive" : "negative"}">${scorecard.expected_profit >= 0 ? "+" : "−"}${money(Math.abs(scorecard.expected_profit))}</b></div><div><span>SESSION CAPITAL</span><b>${money(scorecard.starting_capital)}</b></div></section>
    <section class="score-list"><div class="score-list-heading"><div><span class="eyebrow-small">PITCH BY PITCH</span><h2>What the numbers say</h2></div><span class="mono muted">FIVE Cs · SIMULATED DATA</span></div>${rows}</section>
    <div class="scorecard-caveat">${esc(scorecard.notice)} Founder profiles use synthetic CRS persona facts; business metrics and outcomes are fictional.</div><div class="score-actions"><button type="button" id="play-again" class="primary-button">RUN IT BACK <span class="button-arrow">↗</span></button><button type="button" id="home-button" class="text-button">BACK TO LOBBY</button></div><footer class="game-footer"><span>SHRIMP TANK · UNDERWRITING LAB</span><span>SIMULATED EDUCATIONAL EXPERIENCE</span></footer></div><div id="toast" class="toast" role="status" aria-live="polite"></div>`;
  document.querySelector<HTMLButtonElement>("#play-again")!.addEventListener("click", startGame);
  document.querySelector<HTMLButtonElement>("#home-button")!.addEventListener("click", () => { localStorage.removeItem("credit-tank-session"); renderLanding(); });
}

async function resumeLastSession() {
  const invitedId = new URLSearchParams(location.hash.replace(/^#/, "")).get("room");
  if (invitedId) localStorage.setItem("credit-tank-session", invitedId);
  const id = invitedId || localStorage.getItem("credit-tank-session");
  if (!id) return false;
  try {
    game = personalizeGameState(await api<GameState>(`/api/sessions/${id}`));
    connectRoom(game.id);
    if (game.phase === "complete") renderScorecard();
    else if (game.phase === "pitch_result") renderPitchResult();
    else renderGame();
    return true;
  } catch {
    localStorage.removeItem("credit-tank-session");
    if (invitedId) {
      history.replaceState(null, "", `${location.pathname}${location.search}`);
      toast("That shared game invite is expired or unavailable. Ask the host for a current link.");
    }
    return false;
  }
}

renderLanding();
void resumeLastSession();

