import { schema, table, t, type InferSchema, type ReducerCtx } from "spacetimedb/server";
import { ScheduleAt } from "spacetimedb";

const SESSION_IDLE_TIMEOUT_MS = 2 * 60 * 60 * 1000;
const CLEANUP_INTERVAL_MICROS = 20n * 60n * 1_000_000n;

// Session payloads remain private: they include hidden fictional borrower
// profiles and must only be read by the FastAPI service using the database
// owner's token.
const gameSession = table(
  { name: "game_session" },
  {
    sessionId: t.string().primaryKey(),
    stateJson: t.string(),
    updatedAt: t.string(),
  },
);

const ConversationMessageInput = t.object("ConversationMessageInput", {
  messageId: t.string(),
  sessionId: t.string(),
  pitchId: t.string(),
  pitchIndex: t.u32(),
  sequence: t.u32(),
  roundNumber: t.u8(),
  speaker: t.string(),
  kind: t.string(),
  text: t.string(),
  source: t.string(),
});

// One durable row per utterance, keyed for replay in session/pitch order.
// Keep it private until multiplayer membership and visibility rules are in place.
const conversationMessage = table(
  {
    name: "conversation_message",
    indexes: [{ accessor: "by_session_pitch_sequence", algorithm: "btree", columns: ["sessionId", "pitchIndex", "sequence"] }],
  },
  {
    messageId: t.string().primaryKey(),
    sessionId: t.string(),
    pitchId: t.string(),
    pitchIndex: t.u32(),
    sequence: t.u32(),
    roundNumber: t.u8(),
    speaker: t.string(),
    kind: t.string(),
    text: t.string(),
    source: t.string(),
  },
);

const sessionCleanupSchedule = table(
  { name: "session_cleanup_schedule" },
  {
    scheduledId: t.u64().primaryKey().autoInc(),
    scheduledAt: t.scheduleAt(),
  },
);

const spacetimedb = schema({ gameSession, conversationMessage, sessionCleanupSchedule });
export default spacetimedb;

type Ctx = ReducerCtx<InferSchema<typeof spacetimedb>>;
type ConversationMessageRow = {
  messageId: string;
  sessionId: string;
  pitchId: string;
  pitchIndex: number;
  sequence: number;
  roundNumber: number;
  speaker: string;
  kind: string;
  text: string;
  source: string;
};

function upsertGameSession(ctx: Ctx, sessionId: string, stateJson: string, updatedAt: string, expectedUpdatedAt: string) {
  const existing = ctx.db.gameSession.sessionId.find(sessionId);
  if (existing) {
    if (existing.updatedAt !== expectedUpdatedAt) {
      throw new Error("Session was updated by another request. Reload and retry.");
    }
    ctx.db.gameSession.sessionId.update({ ...existing, stateJson, updatedAt });
    return;
  }
  if (expectedUpdatedAt !== "") {
    throw new Error("Session does not exist at the expected version.");
  }
  ctx.db.gameSession.insert({ sessionId, stateJson, updatedAt });
}

function upsertConversationMessages(ctx: Ctx, messages: ConversationMessageRow[]) {
  for (const message of messages) {
    const existing = ctx.db.conversationMessage.messageId.find(message.messageId);
    if (!existing) {
      ctx.db.conversationMessage.insert(message);
      continue;
    }
    const changed = Object.keys(message).some((key) =>
      existing[key as keyof ConversationMessageRow] !== message[key as keyof ConversationMessageRow]
    );
    if (changed) ctx.db.conversationMessage.messageId.update(message);
  }
}

function deleteStoredSession(ctx: Ctx, sessionId: string): number {
  let messagesDeleted = 0;
  for (const message of [...ctx.db.conversationMessage.by_session_pitch_sequence.filter(sessionId)]) {
    ctx.db.conversationMessage.messageId.delete(message.messageId);
    messagesDeleted += 1;
  }
  ctx.db.gameSession.sessionId.delete(sessionId);
  return messagesDeleted;
}

function ensureCleanupSchedule(ctx: Ctx) {
  if (!ctx.db.sessionCleanupSchedule.scheduledId.find(1n)) {
    ctx.db.sessionCleanupSchedule.insert({
      scheduledId: 1n,
      scheduledAt: ScheduleAt.interval(CLEANUP_INTERVAL_MICROS),
    });
  }
}

function removeExpiredSessions(ctx: Ctx) {
  const cutoffMs = Number(ctx.timestamp.microsSinceUnixEpoch / 1000n) - SESSION_IDLE_TIMEOUT_MS;
  let sessionsDeleted = 0;
  let messagesDeleted = 0;
  for (const session of [...ctx.db.gameSession.iter()]) {
    const lastUpdatedMs = Date.parse(session.updatedAt);
    // Preserve malformed timestamps rather than guessing whether a session is stale.
    if (!Number.isFinite(lastUpdatedMs) || lastUpdatedMs >= cutoffMs) continue;
    messagesDeleted += deleteStoredSession(ctx, session.sessionId);
    sessionsDeleted += 1;
  }
  console.log(`Session cleanup removed ${sessionsDeleted} sessions and ${messagesDeleted} messages.`);
}

export const init = spacetimedb.init((ctx) => {
  ensureCleanupSchedule(ctx);
});

// Also enables the schedule when upgrading an existing database (init does not rerun).
export const cleanupExpiredSessions = spacetimedb.reducer((ctx) => {
  ensureCleanupSchedule(ctx);
  removeExpiredSessions(ctx);
});

export const sweepExpiredSessions = spacetimedb.reducer(
  { onSchedule: sessionCleanupSchedule },
  { timer: sessionCleanupSchedule.rowType },
  (ctx) => {
    if (!ctx.sender.equals(ctx.databaseIdentity)) {
      throw new Error("Session sweeps must be invoked by the database scheduler.");
    }
    removeExpiredSessions(ctx);
  },
);

export const upsertSession = spacetimedb.reducer(
  { sessionId: t.string(), stateJson: t.string(), updatedAt: t.string(), expectedUpdatedAt: t.string() },
  (ctx, { sessionId, stateJson, updatedAt, expectedUpdatedAt }) => {
    upsertGameSession(ctx, sessionId, stateJson, updatedAt, expectedUpdatedAt);
  },
);

// Session state and its current transcript snapshot are committed atomically.
export const upsertSessionWithMessages = spacetimedb.reducer(
  {
    sessionId: t.string(),
    stateJson: t.string(),
    updatedAt: t.string(),
    expectedUpdatedAt: t.string(),
    conversationMessages: t.array(ConversationMessageInput),
  },
  (ctx, { sessionId, stateJson, updatedAt, expectedUpdatedAt, conversationMessages }) => {
    upsertGameSession(ctx, sessionId, stateJson, updatedAt, expectedUpdatedAt);
    upsertConversationMessages(ctx, conversationMessages);
  },
);

export const deleteSession = spacetimedb.reducer(
  { sessionId: t.string() },
  (ctx, { sessionId }) => {
    deleteStoredSession(ctx, sessionId);
  },
);
