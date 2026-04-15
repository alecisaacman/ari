import { getDatabase } from "@/src/core/db/database";
import {
  isCanonicalMemoryType,
  listCanonicalMemoriesByTypes,
  searchCanonicalMemories,
  LOCAL_MEMORY_TYPES,
  rememberCanonicalMemory
} from "@/src/core/ari-spine/memory-bridge";
import {
  createCanonicalTask,
  getCanonicalTaskById,
  listCanonicalTasks,
  searchCanonicalTasks
} from "@/src/core/ari-spine/tasks-bridge";
import { listCanonicalCoordinationRecords } from "@/src/core/ari-spine/coordination-bridge";
import type { DecisionRecord, HistoryRecord, MemoryRecord, MemoryType, MessageRecord, TaskRecord } from "@/src/core/memory/types";

function now(): string {
  return new Date().toISOString();
}

function parseTags(rawTags: string): string[] {
  try {
    const parsed = JSON.parse(rawTags) as string[];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function scoreMemoryRecord(record: MemoryRecord, normalizedQuery: string, words: string[]): number {
  const haystack = `${record.title} ${record.content} ${JSON.stringify(record.tags)}`.toLowerCase();
  let score = 0;
  for (const word of words) {
    if (haystack.includes(word)) {
      score += 2;
    }
  }
  if (record.title.toLowerCase().includes(normalizedQuery)) {
    score += 3;
  }
  if (record.content.toLowerCase().includes(normalizedQuery)) {
    score += 2;
  }
  return score;
}

function saveLocalMemory(type: MemoryType, title: string, content: string, tags: string[] = []): MemoryRecord {
  const database = getDatabase();
  const timestamp = now();
  const record: MemoryRecord = {
    id: crypto.randomUUID(),
    type,
    title,
    content,
    tags,
    createdAt: timestamp,
    updatedAt: timestamp
  };

  database
    .prepare("INSERT INTO memories (id, type, title, content, tags, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)")
    .run(record.id, record.type, record.title, record.content, JSON.stringify(record.tags), record.createdAt, record.updatedAt);

  return record;
}

function listLocalMemoriesByTypes(types: MemoryType[], limit: number): MemoryRecord[] {
  if (!types.length) {
    return [];
  }

  const database = getDatabase();
  const placeholders = types.map(() => "?").join(", ");
  const rows = database
    .prepare(
      `SELECT id, type, title, content, tags, created_at, updated_at
       FROM memories
       WHERE type IN (${placeholders})
       ORDER BY updated_at DESC
       LIMIT ?`
    )
    .all(...types, limit) as Array<{
    id: string;
    type: MemoryType;
    title: string;
    content: string;
    tags: string;
    created_at: string;
    updated_at: string;
  }>;

  return rows.map((row) => ({
    id: row.id,
    type: row.type,
    title: row.title,
    content: row.content,
    tags: parseTags(row.tags),
    createdAt: row.created_at,
    updatedAt: row.updated_at
  }));
}

function searchLocalMemories(query: string, limit: number): MemoryRecord[] {
  const database = getDatabase();
  const normalizedQuery = query.trim().toLowerCase();
  const words = normalizedQuery.split(/\s+/).filter(Boolean);
  const localTypes = Array.from(LOCAL_MEMORY_TYPES);
  const placeholders = localTypes.map(() => "?").join(", ");

  const rows = database
    .prepare(
      `SELECT id, type, title, content, tags, created_at, updated_at
       FROM memories
       WHERE type IN (${placeholders})
       ORDER BY updated_at DESC
       LIMIT 100`
    )
    .all(...localTypes) as Array<{
    id: string;
    type: MemoryType;
    title: string;
    content: string;
    tags: string;
    created_at: string;
    updated_at: string;
  }>;

  return rows
    .map((row) => ({
      id: row.id,
      type: row.type,
      title: row.title,
      content: row.content,
      tags: parseTags(row.tags),
      createdAt: row.created_at,
      updatedAt: row.updated_at
    }))
    .map((record) => ({ record, score: scoreMemoryRecord(record, normalizedQuery, words) }))
    .filter((item) => item.score > 0 || normalizedQuery.length === 0)
    .sort((left, right) => right.score - left.score || right.record.updatedAt.localeCompare(left.record.updatedAt))
    .slice(0, limit)
    .map((item) => item.record);
}

export function ensureConversation(conversationId: string | undefined, source: string): string {
  const database = getDatabase();
  const id = conversationId || crypto.randomUUID();
  const timestamp = now();
  const existing = database
    .prepare("SELECT id FROM conversations WHERE id = ?")
    .get(id) as { id: string } | undefined;

  if (!existing) {
    database
      .prepare("INSERT INTO conversations (id, source, created_at, updated_at) VALUES (?, ?, ?, ?)")
      .run(id, source, timestamp, timestamp);
  } else {
    database.prepare("UPDATE conversations SET updated_at = ? WHERE id = ?").run(timestamp, id);
  }

  return id;
}

export function appendMessage(conversationId: string, role: "user" | "assistant", content: string): MessageRecord {
  const database = getDatabase();
  const record: MessageRecord = {
    id: crypto.randomUUID(),
    conversationId,
    role,
    content,
    createdAt: now()
  };

  database
    .prepare("INSERT INTO messages (id, conversation_id, role, content, created_at) VALUES (?, ?, ?, ?, ?)")
    .run(record.id, record.conversationId, record.role, record.content, record.createdAt);
  database.prepare("UPDATE conversations SET updated_at = ? WHERE id = ?").run(record.createdAt, conversationId);
  return record;
}

export function getRecentMessages(conversationId: string | undefined, limit = 8): MessageRecord[] {
  if (!conversationId) {
    return [];
  }

  const database = getDatabase();
  const rows = database
    .prepare(
      `SELECT id, conversation_id, role, content, created_at
       FROM messages
       WHERE conversation_id = ?
       ORDER BY created_at DESC
       LIMIT ?`
    )
    .all(conversationId, limit) as Array<{
    id: string;
    conversation_id: string;
    role: "user" | "assistant";
    content: string;
    created_at: string;
  }>;

  return rows
    .map((row) => ({
      id: row.id,
      conversationId: row.conversation_id,
      role: row.role,
      content: row.content,
      createdAt: row.created_at
    }))
    .reverse();
}

export function saveMemory(type: MemoryType, title: string, content: string, tags: string[] = []): MemoryRecord {
  if (isCanonicalMemoryType(type)) {
    return rememberCanonicalMemory(type, title, content, tags);
  }
  return saveLocalMemory(type, title, content, tags);
}

export function rememberMemory(type: MemoryType, title: string, content: string, tags: string[] = []): MemoryRecord {
  if (!isCanonicalMemoryType(type)) {
    return saveLocalMemory(type, title, content, tags);
  }
  return rememberCanonicalMemory(type, title, content, tags);
}

export function retrieveMemories(query: string, limit = 5): MemoryRecord[] {
  const normalizedQuery = query.trim().toLowerCase();
  const words = normalizedQuery.split(/\s+/).filter(Boolean);
  const canonicalTypes = (["fact", "preference", "identity", "goal", "active_project", "priority", "routine", "operating_principle", "approval_decision", "working_state"] satisfies MemoryType[]);
  const combined = [...searchCanonicalMemories(query, 100, canonicalTypes), ...searchLocalMemories(query, 100)];

  return combined
    .map((record) => ({ record, score: scoreMemoryRecord(record, normalizedQuery, words) }))
    .filter((item) => item.score > 0 || normalizedQuery.length === 0)
    .sort((left, right) => right.score - left.score || right.record.updatedAt.localeCompare(left.record.updatedAt))
    .slice(0, limit)
    .map((item) => item.record);
}

export function listMemoriesByTypes(types: MemoryType[], limit = 12): MemoryRecord[] {
  if (!types.length) {
    return [];
  }

  const canonicalTypes = types.filter(isCanonicalMemoryType);
  const localTypes = types.filter((type) => !isCanonicalMemoryType(type));
  return [...listCanonicalMemoriesByTypes(canonicalTypes, limit), ...listLocalMemoriesByTypes(localTypes, limit)]
    .sort((left, right) => right.updatedAt.localeCompare(left.updatedAt))
    .slice(0, limit);
}

export function listRecentConversationHistory(limit = 12): MessageRecord[] {
  const database = getDatabase();
  const rows = database
    .prepare(
      `SELECT id, conversation_id, role, content, created_at
       FROM messages
       ORDER BY created_at DESC
       LIMIT ?`
    )
    .all(limit) as Array<{
    id: string;
    conversation_id: string;
    role: "user" | "assistant";
    content: string;
    created_at: string;
  }>;

  return rows.map((row) => ({
    id: row.id,
    conversationId: row.conversation_id,
    role: row.role,
    content: row.content,
    createdAt: row.created_at
  }));
}

export function listRecentDecisions(limit = 8): DecisionRecord[] {
  const database = getDatabase();
  const approvals = database
    .prepare(
      `SELECT id, title, resolution_note, resolved_at
       FROM approvals
       WHERE status IN ('approved', 'denied')
       ORDER BY resolved_at DESC
       LIMIT ?`
    )
    .all(limit) as Array<{
    id: string;
    title: string;
    resolution_note: string;
    resolved_at: string | null;
  }>;

  const orchestration = listCanonicalCoordinationRecords<{
    id: string;
    concise_summary: string;
    alec_decision: string;
    processed_at: string | null;
    created_at: string;
  }>("orchestration_record", 40)
    .filter((row) => row.alec_decision.trim())
    .sort((left, right) => (right.processed_at || right.created_at).localeCompare(left.processed_at || left.created_at))
    .slice(0, limit);

  return [
    ...approvals.map((row) => ({
      id: row.id,
      title: row.title,
      body: row.resolution_note,
      source: "approval" as const,
      createdAt: row.resolved_at || now()
    })),
    ...orchestration.map((row) => ({
      id: row.id,
      title: row.concise_summary || "Alec decision recorded",
      body: row.alec_decision,
      source: "orchestration" as const,
      createdAt: row.processed_at || row.created_at
    }))
  ]
    .sort((left, right) => right.createdAt.localeCompare(left.createdAt))
    .slice(0, limit);
}

export function listRecentHistory(limit = 16): HistoryRecord[] {
  const database = getDatabase();
  const messages = database
    .prepare(
      `SELECT id, role, content, created_at
       FROM messages
       ORDER BY created_at DESC
       LIMIT ?`
    )
    .all(limit) as Array<{
    id: string;
    role: "user" | "assistant";
    content: string;
    created_at: string;
  }>;
  const events = database
    .prepare(
      `SELECT id, title, body, created_at
       FROM ari_events
       ORDER BY created_at DESC
       LIMIT ?`
    )
    .all(limit) as Array<{
    id: string;
    title: string;
    body: string;
    created_at: string;
  }>;
  const decisions = listRecentDecisions(limit);

  return [
    ...messages.map((row) => ({
      id: row.id,
      type: "message" as const,
      title: row.role === "user" ? "User message" : "ARI response",
      body: row.content,
      createdAt: row.created_at
    })),
    ...events.map((row) => ({
      id: row.id,
      type: "event" as const,
      title: row.title,
      body: row.body,
      createdAt: row.created_at
    })),
    ...decisions.map((row) => ({
      id: row.id,
      type: row.source === "approval" ? ("approval" as const) : ("orchestration" as const),
      title: row.title,
      body: row.body,
      createdAt: row.createdAt
    }))
  ]
    .sort((left, right) => right.createdAt.localeCompare(left.createdAt))
    .slice(0, limit);
}

export function createTask(title: string, notes = ""): TaskRecord {
  return createCanonicalTask(title, notes);
}

export function listTasks(limit = 20): TaskRecord[] {
  return listCanonicalTasks(limit);
}

export function findLatestTaskByTitle(title: string): TaskRecord | null {
  const exact = searchCanonicalTasks(title, 20).filter((task) => task.title === title);
  return exact[0] || null;
}

export function getTaskById(id: string): TaskRecord | null {
  return getCanonicalTaskById(id);
}

export function logToolRun(toolName: string, status: "ok" | "error", input: unknown, output: unknown): void {
  const database = getDatabase();
  database
    .prepare("INSERT INTO tool_runs (id, tool_name, status, input_json, output_json, created_at) VALUES (?, ?, ?, ?, ?, ?)")
    .run(crypto.randomUUID(), toolName, status, JSON.stringify(input), JSON.stringify(output), now());
}
