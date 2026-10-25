import "./style.css";
import type { Stage } from "./stage";

type Message = { id: string; speaker: string; text: string; kind: string; round: number };
type GameState = {
  id: string; phase: string; difficulty: string; total_pitches: number; pitch_index: number; round: number; max_rounds: number;
  balance: number; starting_capital: number; pitch: any; messages: Message[]; disclosures: string[]; offers: any[];
  sharks: any[]; question_asked: boolean; human_out: boolean; result: any; scorecard: any; ai_mode: string;
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
const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";
let game: GameState | null = null;
let selectedDifficulty = "medium";
let selectedPitchCount = 4;
let busy = false;
let readingUntil = 0;
let toastTimer = 0;
let speechTimer = 0;
let speechToken = 0;
let speechActive = false;
let readingTickTimer = 0;
let wasReadingLocked = false;
const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
const SPEECH_BUBBLE_DURATION_MS = 4000;
const SPEECH_BUBBLE_GAP_MS = 2000;

const money = (value: number) => new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(value || 0);
const esc = (value: unknown) => String(value ?? "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]!);

async function api<T = any>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init.headers || {}) },
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
      headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
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
  return questionPause + incoming.length * SPEECH_BUBBLE_DURATION_MS + Math.max(0, incoming.length - 1) * SPEECH_BUBBLE_GAP_MS;
}

function holdForDialogue(messages: Message[]) {
  readingUntil = Date.now() + dialogueDuration(messages);
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
    showPlayerSpeech(playerQuestion.text);
    stage?.setSpeaker(-1);
    announce(`You asked: ${playerQuestion.text}`);
  }
  const incoming = messages.filter((message) => message.kind !== "question");
  if (reducedMotion.matches) {
    if (playerQuestion) {
      speechTimer = window.setTimeout(() => { if (token === speechToken) showPlayerSpeech(""); }, 900);
    }
    return;
  }
  if (!incoming.length) {
    if (playerQuestion) speechTimer = window.setTimeout(() => showPlayerSpeech(""), 900);
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
      stage?.setSpeaker(null);
      displayReadingLock();
      return;
    }
    const article = document.getElementById(`message-${message.id}`);
    const body = article?.querySelector<HTMLElement>(".message-text, .stage-message-text");
    if (!article || !body) { next(); return; }
    article.classList.remove("pending-message");
    article.classList.add("speaking");
    body.textContent = "";
    const sharkIndex = game?.sharks.findIndex((shark: any) => shark.name === message.speaker) ?? -1;
    stage?.setSpeaker(message.kind === "round" ? null : sharkIndex >= 0 ? sharkIndex + 1 : 0, "");
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
      stage?.updateSpeech(visibleText);
      transcript?.scrollTo({ top: transcript.scrollHeight, behavior: "auto" });
      if (elapsed < SPEECH_BUBBLE_DURATION_MS) {
        speechTimer = window.setTimeout(type, Math.min(50, SPEECH_BUBBLE_DURATION_MS - elapsed));
        return;
      }
      body.textContent = message.text;
      article.setAttribute("aria-label", `${message.speaker}: ${message.text}`);
      article.classList.remove("speaking");
      announce(`${message.speaker}: ${message.text}`);
      stage?.setSpeaker(null);
      speechTimer = window.setTimeout(next, current < incoming.length ? SPEECH_BUBBLE_GAP_MS : 0);
    };
    type();
  };
  if (playerQuestion) speechTimer = window.setTimeout(next, 850);
  else next();
  displayReadingLock();
}

function renderLanding() {
  stopSpeech();
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
            <p class="setup-note"><span>✳</span> Fictional scenarios · No real credit decisions</p>
          </div>
        </div>
        <div class="hero-scene" aria-hidden="true">
          <div class="scene-vignette"></div>
          <div class="hero-kicker"><span class="kicker-index">01</span><span>THE BORROWER IS IN</span></div>
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
}

async function startGame() {
  if (busy) return;
  const button = document.querySelector<HTMLButtonElement>("#start-game") || document.querySelector<HTMLButtonElement>("#play-again");
  busy = true;
  if (button) { button.disabled = true; button.innerHTML = "<span>PREPARING THE TANK…</span><span class=\"spinner\"></span>"; }
  let cutscene: HTMLElement | null = null;
  try {
    await stageReady;
    if (stage) {
      cutscene = document.createElement("section");
      cutscene.className = "intro-cutscene";
      cutscene.setAttribute("aria-label", "Opening cutscene");
      cutscene.innerHTML = `
        <div id="cutscene-stage" class="cutscene-stage" aria-hidden="true"></div>
        <div class="cutscene-topline" aria-live="polite"><span>SHRIMP TANK · OPENING SEQUENCE</span><b id="cutscene-shot">CAM 01 · BACKSTAGE ENTRY</b></div>
        <div class="cutscene-bottomline"><span id="cutscene-caption">THE PRESENTER IS ENTERING THE HALLWAY</span><button type="button" id="skip-intro" class="skip-intro">SKIP CUTSCENE <span>↗</span></button></div>
        <p class="sr-only">The presenter enters through backstage doors, walks down the hallway, and comes onto the stage. You can skip the cutscene.</p>`;
      ui.append(cutscene);
      stage.mount(cutscene.querySelector<HTMLElement>("#cutscene-stage")!);
      const shotLabel = cutscene.querySelector<HTMLElement>("#cutscene-shot")!;
      const caption = cutscene.querySelector<HTMLElement>("#cutscene-caption")!;
      const shotNames: [string, string][] = [
        ["CAM 01 · BACKSTAGE ENTRY", "THE PRESENTER IS ENTERING THE HALLWAY"],
        ["CAM 02 · HALLWAY TO STAGE", "THE PRESENTER WALKS THROUGH THE STAGE DOORS"],
        ["CAM 03 · INVESTOR POV", "THE PRESENTER IS ENTERING THE SET"],
        ["CAM 03 · INVESTOR POV", "THE PRESENTER HAS TAKEN THE STAGE"],
      ];
      await new Promise<void>((resolve) => {
        cutscene!.querySelector<HTMLButtonElement>("#skip-intro")!.addEventListener("click", () => stage?.skipIntro(), { once: true });
        stage!.intro(resolve, (shot) => {
          const labels = shotNames[shot] || shotNames[0];
          if (!labels) return;
          shotLabel.textContent = labels[0];
          caption.textContent = labels[1];
        });
      });
    }
    if (button) button.innerHTML = "<span>SETTING THE TABLE…</span><span class=\"spinner\"></span>";
    game = await api<GameState>("/api/sessions", { method: "POST", body: JSON.stringify({ total_pitches: selectedPitchCount, difficulty: selectedDifficulty }) });
    cutscene?.remove();
    localStorage.setItem("credit-tank-session", game.id);
    holdForDialogue(game.messages);
    stage?.setPitch(game.pitch.archetype, game.pitch.company);
    busy = false;
    renderGame(game.messages);
  } catch (error) {
    cutscene?.remove();
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
    const locked = remaining > 0 || conversationLocked;
    controls.forEach((control) => {
      const ownDisabled = control.dataset.intrinsicDisabled === "true";
      control.disabled = busy || ownDisabled || remaining > 0 || conversationLocked;
    });
    if (label) label.textContent = remaining > 0 ? `READ THE ROOM · ${Math.ceil(remaining / 1000)}s` : conversationLocked ? "HEAR THE FULL TABLE" : "YOUR MOVE";
    if (reveal) {
      const readyToReveal = remaining <= 0 && !speechActive;
      reveal.textContent = readyToReveal ? "REVEAL FOUNDER'S DECISION ↗" : "SHOW TRANSCRIPT & REVEAL DECISION ↗";
    }
    if (wasReadingLocked && !locked) announce(game?.question_asked ? "The conversation is complete. You may submit an offer or pass." : "Your move. You may ask a question or make an offer.");
    wasReadingLocked = locked;
    if (remaining > 0) readingTickTimer = window.setTimeout(tick, Math.min(1000, remaining));
  };
  tick();
}

function renderGame(animateMessages: Message[] = []) {
  stopSpeech();
  if (!game) return;
  stage?.setPitch(game.pitch.archetype, game.pitch.company);
  if (game.phase === "complete") { renderScorecard(); return; }
  if (game.phase === "pitch_result") { renderPitchResult(); return; }
  const incomingIds = new Set(reducedMotion.matches ? [] : animateMessages.filter((message) => message.kind !== "question").map((message) => message.id));
  const aiBadge = game.ai_mode === "offline" ? "GROK KEY NEEDED" : "GROK LIVE DIALOGUE";
  const messages = game.messages.map((message) => {
    const investor = game!.sharks.find((shark: any) => shark.name === message.speaker);
    const speakerLabel = investor ? `${message.speaker} (${investor.title})` : message.speaker;
    return `
    <article id="message-${esc(message.id)}" role="group" aria-label="${esc(`${speakerLabel}: ${message.text}`)}" class="message ${message.kind === "question" ? "from-you" : message.kind === "shark_question" || message.kind === "offer" ? "from-shark" : message.kind === "round" ? "stage-message" : "from-founder"} ${incomingIds.has(message.id) ? "pending-message" : ""}">
      ${message.kind === "round" ? `<p class="stage-message-text">${incomingIds.has(message.id) ? "" : esc(message.text)}</p>` : `<div class="message-meta"><span class="speaker">${esc(message.speaker)}</span>${investor ? `<span class="speaker-personality">(${esc(investor.title)})</span>` : ""}</div><p class="message-text">${incomingIds.has(message.id) ? "" : esc(message.text)}</p>`}
    </article>`;
  }).join("");
  const disclosures = game.disclosures.length ? game.disclosures.map((key: string) => `<span class="clue-chip found">${esc(key)}</span>`).join("") : `<span class="clue-empty">Nothing surfaced yet.</span>`;
  const offerRows = game.offers.length ? game.offers.map((offer: any) => `
    <div class="offer-row"><div><span class="offer-name">${esc(offer.investor)}</span><small>${offer.secured ? "SECURED" : "UNSECURED"} · ${offer.term_months} MO</small></div><div class="offer-numbers"><b>${money(offer.amount)}</b><small>${Number(offer.rate).toFixed(1)}% APR${offer.royalty ? ` · ${offer.royalty}% REV` : ""}</small></div></div>`).join("") : `<div class="empty-offers"><span class="empty-offer-icon">↗</span><span>No active offers</span><small>The table is still open.</small></div>`;
  const decisionRequired = game.question_asked && game.phase === "investigate";
  const pitchReview = game.phase === "pitch_review";

  ui.innerHTML = `
    <div class="game-shell has-full-scene">
      <div id="game-stage" class="game-stage" aria-hidden="true"></div>
      <div id="player-speech-bubble" class="player-speech-bubble" hidden><p></p></div>
      <a class="skip-link" href="#conversation-panel">Skip to the conversation</a>
      <header class="game-topbar">
        <a class="brand compact" href="#"><span class="brand-mark">ST</span><span>SHRIMP TANK<small>UNDERWRITING LAB</small></span></a>
        <div class="session-progress"><div class="progress-label"><span>SESSION PROGRESS</span><b>${String(game.pitch_index).padStart(2, "0")} <i>/</i> ${String(game.total_pitches).padStart(2, "0")}</b></div><div class="progress-track"><span style="width:${game.pitch_index / game.total_pitches * 100}%"></span></div></div>
        <div class="capital-pill"><span>AVAILABLE CAPITAL</span><b>${money(game.balance)}</b></div>
        <div class="game-status"><span class="live-dot"></span><span>${aiBadge}</span></div>
        <button type="button" id="debug-reset" class="debug-reset-button" aria-label="Reset game, delete this session, and return to setup" title="Reset game and return to setup"><span class="debug-reset-label">DEBUG RESET</span><span aria-hidden="true">↻</span></button>
        <button type="button" class="icon-button exit-button" id="exit-game" aria-label="Exit session">×</button>
      </header>
      <div class="pitch-heading"><div><span class="eyebrow"><span class="eyebrow-line"></span>${esc(game.pitch.archetype)} <span class="dot-sep">·</span> ${esc(game.pitch.sector)}</span><h1>${esc(game.pitch.company)}</h1><p>FOUNDER <b>${esc(game.pitch.founder)}</b><span class="dot-sep">·</span> ASKING <b>${money(game.pitch.ask_amount)}</b></p></div><div class="round-pill"><span>ROUND</span><b>${String(game.round).padStart(2, "0")}<i> / 03</i></b></div></div>
      <section class="game-grid">
        <aside class="side-column left-column">
          <div class="panel company-panel"><div class="panel-label"><span>THE ASK</span><span class="panel-index">01</span></div><div class="ask-value">${money(game.pitch.ask_amount)}</div><div class="ask-purpose">${esc(game.pitch.purpose)}</div><div class="mini-metric"><span>REPORTED ANNUAL REVENUE</span><b>${money(game.pitch.public_revenue)}</b></div><div class="mini-metric"><span>PROPOSED OPENING RATE</span><b>${Number(game.pitch.opening_rate).toFixed(1)}<small>% APR</small></b></div></div>
          <div class="panel ledger-panel"><div class="panel-label"><span>ACTIVE OFFERS</span><span class="panel-index">${String(game.offers.length).padStart(2, "0")}</span></div><div class="offer-list">${offerRows}</div></div>
          <div class="panel discovery-panel"><div class="panel-label"><span>WHAT YOU'VE UNCOVERED</span><span class="panel-index">${String(game.disclosures.length).padStart(2, "0")}</span></div><div class="clue-list">${disclosures}</div></div>
        </aside>
        <section id="conversation-panel" class="panel dialogue-panel" aria-label="Pitch dialogue" tabindex="-1">
          <div class="dialogue-top"><div class="panel-label"><span>THE CONVERSATION</span><span class="conversation-state"><span class="live-dot"></span> ON THE RECORD</span></div><div class="conversation-subtitle">Question the story. Find what the numbers don't say.</div></div>
          <p class="sr-only">A full-screen, low-poly television pitch studio sits behind the game interface. Drag any exposed area of the scene to look around; the interface remains in place.</p>
          <div class="transcript" id="transcript">${messages}<div class="transcript-end" id="transcript-end"></div></div>
          <div class="compose-area">
            ${pitchReview ? `<div class="decision-review" role="status"><span class="round-required-mark">✓</span><div><b>ROUND CLOSED · CONVERSATION PRESERVED</b><p>All messages and offers remain above. Reveal the founder's decision when you are ready, or reveal the full transcript and decision now.</p></div><button type="button" id="reveal-decision" class="primary-button">SHOW TRANSCRIPT & REVEAL DECISION ↗</button></div>` : decisionRequired ? `<div class="round-locked"><span class="round-required-mark">!</span><div><b>YOUR QUESTION HAS BEEN USED</b><p>This round ends with a decision. Use the highlighted decision bar below to submit an offer, pass, or leave.</p></div><a href="#offer-dock" class="decision-banner-action">GO TO DECISION ↓</a></div>` : `<div class="prompt-row"><span>ASK ABOUT</span><button type="button" class="prompt-chip" data-question="What's your personal credit history and current debt?">Credit</button><button type="button" class="prompt-chip" data-question="How much free cash flow do you have after paying suppliers and debt?">Capacity</button><button type="button" class="prompt-chip" data-question="How much have you invested in the business?">Capital</button><button type="button" class="prompt-chip" data-question="What assets could you pledge as collateral?">Collateral</button><button type="button" class="prompt-chip" data-question="Who are your largest customers, and how secure are those orders?">Customers</button></div><form id="question-form" class="question-form"><label class="sr-only" for="question-input">Question for the founder</label><input id="question-input" class="turn-control" data-intrinsic-disabled="false" type="text" maxlength="400" placeholder="Ask your own question…" autocomplete="off" ${busy ? "disabled" : ""} /><button class="send-button turn-control" data-intrinsic-disabled="false" type="submit" aria-label="Ask question" ${busy ? "disabled" : ""}>↗</button></form><div class="turn-bar"><span id="reading-label">YOUR MOVE</span><span>MAX 400 CHARACTERS</span></div>`}
          </div>
        </section>
      </section>
      <section id="offer-dock" class="offer-dock ${decisionRequired ? "round-required" : ""} ${pitchReview ? "review-dock" : ""}"><div class="dock-heading"><div><span class="panel-label">${pitchReview ? "PITCH REVIEW" : "MAKE YOUR MOVE"}</span><span class="dock-subtitle">${pitchReview ? "The founder's decision is intentionally held until the full conversation has been reviewed." : decisionRequired ? "Required now: close this round with an offer, pass, or leave the pitch." : "A loan offer stays active until you revise it or leave the pitch."}</span></div><span class="round-reminder">ROUND ${game.round} / 3</span></div>${pitchReview ? `<div class="review-dock-message">All offers are locked. Use the reveal control at the end of the conversation to see the founder's selection.</div>` : `<form id="offer-form" class="offer-form"><label><span>LOAN AMOUNT</span><div class="money-input"><i>$</i><input id="offer-amount" class="turn-control" type="number" min="25000" max="750000" step="5000" value="${game.pitch.ask_amount}" required /></div></label><label><span>ANNUAL INTEREST</span><div class="number-input"><input id="offer-rate" class="turn-control" type="number" min="0" max="40" step="0.25" value="${Number(game.pitch.opening_rate).toFixed(2)}" required /><i>%</i></div></label><label><span>REVENUE SHARE</span><div class="number-input"><input id="offer-royalty" class="turn-control" type="number" min="0" max="12" step="0.25" value="0" /><i>%</i></div></label><label><span>TERM</span><select id="offer-term" class="select-control turn-control"><option value="24">24 months</option><option value="36" selected>36 months</option><option value="48">48 months</option><option value="60">60 months</option></select></label><label class="secured-control"><input id="offer-secured" class="turn-control" type="checkbox" /><span>SECURED</span></label><button type="submit" class="primary-button offer-submit turn-control" data-intrinsic-disabled="${game.human_out}" ${game.human_out || busy ? "disabled" : ""}>SUBMIT OFFER <span>↗</span></button><button type="button" id="pass-turn" class="text-button turn-control" ${busy ? "disabled" : ""}>PASS</button><button type="button" id="out-turn" class="text-button out-button turn-control" aria-label="Leave the pitch and let the remaining investors continue" data-intrinsic-disabled="${game.human_out}" ${game.human_out || busy ? "disabled" : ""}>I'M OUT · TABLE CONTINUES</button></form><div class="dock-footnote">Interest and revenue share are simulated terms. This game does not issue a loan.</div>`}</section>
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
  document.querySelector<HTMLFormElement>("#offer-form")?.addEventListener("submit", (event) => { event.preventDefault(); submitMove("offer"); });
  document.querySelector<HTMLButtonElement>("#pass-turn")?.addEventListener("click", () => submitMove("pass"));
  document.querySelector<HTMLButtonElement>("#out-turn")?.addEventListener("click", () => submitMove("out"));
  document.querySelector<HTMLButtonElement>("#reveal-decision")?.addEventListener("click", revealDecision);
  document.querySelector<HTMLButtonElement>("#debug-reset")!.addEventListener("click", resetGameToMenu);
  document.querySelector<HTMLButtonElement>("#exit-game")!.addEventListener("click", () => {
    if (window.confirm("Leave this session? Its in-memory state is available until the game server restarts.")) { localStorage.removeItem("credit-tank-session"); renderLanding(); }
  });
  displayReadingLock();
  playDialogue(animateMessages);
}

async function resetGameToMenu() {
  if (!game || busy) return;
  if (!window.confirm("Reset this game, delete its saved session, and return to setup?")) return;
  const sessionId = game.id;
  const button = document.querySelector<HTMLButtonElement>("#debug-reset");
  if (button) button.disabled = true;
  busy = true;
  let cleanupError = "";
  try {
    await api(`/api/sessions/${encodeURIComponent(sessionId)}`, { method: "DELETE" });
  } catch (error) {
    cleanupError = error instanceof Error ? error.message : "The server couldn't delete the saved session.";
  }
  localStorage.removeItem("credit-tank-session");
  busy = false;
  renderLanding();
  if (cleanupError) toast(`Returned to setup, but server cleanup failed: ${cleanupError}`);
}

async function askFounder(event: SubmitEvent) {
  event.preventDefault();
  if (!game || busy || game.question_asked || Date.now() < readingUntil) return;
  const input = document.querySelector<HTMLInputElement>("#question-input")!;
  const question = input.value.trim();
  if (question.length < 2) { toast("Write a question or choose one of the prompts."); return; }
  busy = true;
  renderGame();
  const priorCount = game.messages.length;
  const transcript = document.querySelector<HTMLElement>("#transcript");
  const makeQuestionMessage = () => {
    const article = document.createElement("article");
    article.className = "message from-you";
    article.setAttribute("role", "group");
    article.setAttribute("aria-label", `You: ${question}`);
    const meta = document.createElement("div");
    meta.className = "message-meta";
    const speaker = document.createElement("span");
    speaker.className = "speaker";
    speaker.textContent = "You";
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
    game = await streamQuestion(sessionId, question, (message) => {
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
    });
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
  } finally { busy = false; }
}

async function submitMove(action: "offer" | "pass" | "out") {
  if (!game || busy || Date.now() < readingUntil || (speechActive && game.question_asked && game.phase === "investigate")) return;
  busy = true;
  const previousMessages = game.messages.length;
  const payload: any = { action };
  if (action === "offer") {
    payload.amount = Number(document.querySelector<HTMLInputElement>("#offer-amount")?.value);
    payload.rate = Number(document.querySelector<HTMLInputElement>("#offer-rate")?.value);
    payload.royalty = Number(document.querySelector<HTMLInputElement>("#offer-royalty")?.value || 0);
    payload.term_months = Number(document.querySelector<HTMLSelectElement>("#offer-term")?.value || 36);
    payload.secured = Boolean(document.querySelector<HTMLInputElement>("#offer-secured")?.checked);
  }
  renderGame();
  try {
    game = await api<GameState>(`/api/sessions/${game.id}/decision`, { method: "POST", body: JSON.stringify(payload) });
    const fresh = game.messages.slice(previousMessages);
    if (game.phase === "investigate" || game.phase === "pitch_review") holdForDialogue(fresh);
    else readingUntil = 0;
    busy = false;
    renderGame(fresh);
    if (game.phase === "pitch_review") announce("The round is closed. Review the complete conversation before revealing the founder's decision.");
  } catch (error) {
    busy = false;
    renderGame();
    toast(error instanceof Error ? error.message : "Couldn't submit that move.");
  } finally { busy = false; }
}

async function revealDecision() {
  if (!game || busy || game.phase !== "pitch_review") return;
  if (Date.now() < readingUntil || speechActive) showFullTranscript();
  busy = true;
  const button = document.querySelector<HTMLButtonElement>("#reveal-decision");
  if (button) { button.disabled = true; button.textContent = "REVEALING DECISION…"; }
  try {
    game = await api<GameState>(`/api/sessions/${game.id}/reveal`, { method: "POST", body: "{}" });
    readingUntil = 0;
    renderPitchResult();
    announce("The founder's decision is now revealed.");
  } catch (error) {
    busy = false;
    renderGame();
    toast(error instanceof Error ? error.message : "Couldn't reveal the founder's decision.");
  } finally { busy = false; }
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
    <section class="result-card"><p class="eyebrow"><span class="eyebrow-line"></span>${accepted ? "THE FOUNDER HAS A DEAL" : "THE FOUNDER IS WALKING"}</p><div class="result-symbol ${accepted ? "accepted" : "passed"}">${accepted ? "✓" : "—"}</div><h1>${accepted ? "Deal closed." : "No deal."}</h1><p class="result-company">${esc(game.pitch.company)} <span>·</span> ${esc(game.pitch.archetype)}</p><div class="result-terms"><span>${esc(result.message)}</span><small>RISK GRADE ${result.grade} · ${esc(result.risk_label).toUpperCase()}</small></div><div class="result-actions"><button type="button" id="advance" class="primary-button">${game.pitch_index < game.total_pitches ? "NEXT PITCH" : "VIEW SCORECARD"}<span class="button-arrow">↗</span></button></div><p class="result-note">The detailed five Cs assessment is revealed in your final scorecard.</p></section><footer class="game-footer"><span>FICTIONAL BUSINESS CASE</span><span>NO REAL CREDIT DECISIONS</span></footer></div><div id="toast" class="toast" role="status" aria-live="polite"></div>`;
  document.querySelector<HTMLButtonElement>("#advance")!.addEventListener("click", advance);
}

async function advance() {
  if (!game || busy) return;
  busy = true;
  if (game.pitch_index >= game.total_pitches) {
    try { game = await api<GameState>(`/api/sessions/${game.id}`); renderScorecard(); }
    catch (error) { toast(error instanceof Error ? error.message : "Couldn't load scorecard."); }
    finally { busy = false; }
    return;
  }
  try {
    game = await api<GameState>(`/api/sessions/${game.id}/next`, { method: "POST", body: "{}" });
    stage?.setPitch(game.pitch.archetype, game.pitch.company);
    holdForDialogue(game.messages);
    busy = false;
    renderGame(game.messages);
  } catch (error) { toast(error instanceof Error ? error.message : "Couldn't start the next pitch."); }
  finally { busy = false; }
}

function renderScorecard() {
  if (!game?.scorecard) return;
  stopSpeech();
  window.clearTimeout(readingTickTimer);
  readingUntil = 0;
  wasReadingLocked = false;
  stage?.mount(document.querySelector<HTMLElement>("#stage")!);
  const scorecard = game.scorecard;
  const rows = scorecard.pitches.map((pitch: any) => `
    <article class="score-pitch"><div class="score-pitch-head"><div><span class="eyebrow-small">${esc(pitch.archetype)} · GRADE ${pitch.grade}</span><h3>${esc(pitch.company)}</h3></div><span class="risk-tag grade-${pitch.grade}">${esc(pitch.risk_label)}</span></div><div class="five-cs">${Object.entries(pitch.assessment.components).map(([key, value]) => `<div class="cs-row"><span>${esc(key)}</span><div class="cs-track"><i style="width:${Number(value)}%"></i></div><b>${value}</b></div>`).join("")}</div><div class="score-pitch-details"><div><small>YOUR DECISION</small><b>${pitch.winner === "human_user" ? `FUNDED · ${money(pitch.player_offer?.amount || 0)} @ ${Number(pitch.player_offer?.rate || 0).toFixed(1)}%` : pitch.winner ? `OTHER INVESTOR · ${esc(pitch.decision.replace("_", " ").toUpperCase())}` : "NO DEAL"}</b></div><div><small>RULES-BASED BENCHMARK</small><b>${pitch.benchmark.action === "walk_away" ? "WALK AWAY" : `${money(pitch.benchmark.amount)} @ ${Number(pitch.benchmark.rate).toFixed(1)}%`}</b></div><div><small>EXPECTED GAME P&L</small><b class="${pitch.expected_profit >= 0 ? "positive" : "negative"}">${pitch.expected_profit >= 0 ? "+" : "−"}${money(Math.abs(pitch.expected_profit))}</b></div></div><p class="score-feedback">${esc(pitch.feedback)}</p><details class="evidence-details"><summary>Reveal the founder's fictional profile</summary><div class="evidence-grid"><span>Credit score <b>${pitch.credit_score ?? "No score"}</b></span><span>Derogatory signals <b>${pitch.derogatory_count}</b></span><span>Free cash flow <b>${money(pitch.monthly_free_cash_flow)}/mo</b></span><span>Owner equity <b>${money(pitch.owner_equity)}</b></span><span>Collateral <b>${money(pitch.collateral)}</b></span><span>DSCR <b>${pitch.assessment.dscr}×</b></span></div><p>${esc(pitch.benchmark.reason)}</p></details></article>`).join("");
  ui.innerHTML = `
    <div class="scorecard-shell"><header class="game-topbar"><a class="brand compact" href="#"><span class="brand-mark">ST</span><span>SHRIMP TANK<small>UNDERWRITING LAB</small></span></a><div class="session-progress"><div class="progress-label"><span>SESSION COMPLETE</span><b>${String(game.total_pitches).padStart(2, "0")} <i>/</i> ${String(game.total_pitches).padStart(2, "0")}</b></div><div class="progress-track"><span style="width:100%"></span></div></div><div class="capital-pill"><span>PROJECTED CAPITAL</span><b>${money(scorecard.projected_ending_capital)}</b></div><div class="game-status"><span class="live-dot"></span><span>FINAL REVIEW</span></div></header>
    <section class="score-hero"><div class="score-title"><p class="eyebrow"><span class="eyebrow-line"></span>SESSION DEBRIEF</p><h1>Read the risk.<br /><em>Price the return.</em></h1><p>Your decisions, measured against a transparent teaching benchmark built around the five Cs of credit.</p></div><div class="score-circle"><span>UNDERWRITING<br />INSTINCT</span><b>${scorecard.overall_score}</b><small>OUT OF 100</small></div></section>
    <section class="score-summary"><div><span>DECISION FIT</span><b>${scorecard.decision_accuracy}<small> / 100</small></b></div><div><span>DEALS YOU FUNDED</span><b>${scorecard.deals_funded}<small> / ${game.total_pitches}</small></b></div><div><span>EXPECTED GAME P&L</span><b class="${scorecard.expected_profit >= 0 ? "positive" : "negative"}">${scorecard.expected_profit >= 0 ? "+" : "−"}${money(Math.abs(scorecard.expected_profit))}</b></div><div><span>SESSION CAPITAL</span><b>${money(scorecard.starting_capital)}</b></div></section>
    <section class="score-list"><div class="score-list-heading"><div><span class="eyebrow-small">PITCH BY PITCH</span><h2>What the numbers say</h2></div><span class="mono muted">FIVE Cs · SIMULATED DATA</span></div>${rows}</section>
    <div class="scorecard-caveat">${esc(scorecard.notice)} Founder profiles use synthetic CRS persona facts; business metrics and outcomes are fictional.</div><div class="score-actions"><button type="button" id="play-again" class="primary-button">RUN IT BACK <span class="button-arrow">↗</span></button><button type="button" id="home-button" class="text-button">BACK TO LOBBY</button></div><footer class="game-footer"><span>SHRIMP TANK · UNDERWRITING LAB</span><span>SIMULATED EDUCATIONAL EXPERIENCE</span></footer></div><div id="toast" class="toast" role="status" aria-live="polite"></div>`;
  document.querySelector<HTMLButtonElement>("#play-again")!.addEventListener("click", startGame);
  document.querySelector<HTMLButtonElement>("#home-button")!.addEventListener("click", () => { localStorage.removeItem("credit-tank-session"); renderLanding(); });
}

async function resumeLastSession() {
  const id = localStorage.getItem("credit-tank-session");
  if (!id) return false;
  try {
    game = await api<GameState>(`/api/sessions/${id}`);
    if (game.phase === "complete") renderScorecard();
    else if (game.phase === "pitch_result") renderPitchResult();
    else renderGame();
    return true;
  } catch {
    localStorage.removeItem("credit-tank-session");
    return false;
  }
}

renderLanding();
void resumeLastSession();

