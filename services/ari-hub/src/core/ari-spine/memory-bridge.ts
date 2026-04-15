import type { MemoryRecord, MemoryType } from "@/src/core/memory/types";
import { isSubprocessBridgeMode, requestAriApiSync, runCanonicalJsonCommand } from "@/src/core/ari-spine/api-client";

export const LOCAL_MEMORY_TYPES = new Set<MemoryType>(["note", "episodic_history", "conversation_history"]);

function parseCanonicalMemory(payload: {
  id: string;
  type: MemoryType;
  title: string;
  content: string;
  tags: string[];
  created_at: string;
  updated_at: string;
}): MemoryRecord {
  return {
    id: String(payload.id),
    type: payload.type,
    title: payload.title,
    content: payload.content,
    tags: Array.isArray(payload.tags) ? payload.tags : [],
    createdAt: payload.created_at,
    updatedAt: payload.updated_at
  };
}

export function isCanonicalMemoryType(type: MemoryType): boolean {
  return !LOCAL_MEMORY_TYPES.has(type);
}

export function rememberCanonicalMemory(type: MemoryType, title: string, content: string, tags: string[] = []): MemoryRecord {
  const payload = isSubprocessBridgeMode()
    ? runCanonicalJsonCommand<{
        id: string;
        type: MemoryType;
        title: string;
        content: string;
        tags: string[];
        created_at: string;
        updated_at: string;
      }>(["api", "memory", "remember", "--type", type, "--title", title, "--body", content, "--tags-json", JSON.stringify(tags), "--json"])
    : requestAriApiSync<{
        id: string;
        type: MemoryType;
        title: string;
        content: string;
        tags: string[];
        created_at: string;
        updated_at: string;
      }>("POST", "/memory", {
        body: { type, title, content, tags }
      });

  return parseCanonicalMemory(payload);
}

export function listCanonicalMemoriesByTypes(types: MemoryType[], limit = 20): MemoryRecord[] {
  if (!types.length) {
    return [];
  }

  const payload = isSubprocessBridgeMode()
    ? runCanonicalJsonCommand<{
        memories: Array<{
          id: string;
          type: MemoryType;
          title: string;
          content: string;
          tags: string[];
          created_at: string;
          updated_at: string;
        }>;
      }>(["api", "memory", "list", ...types.flatMap((type) => ["--type", type]), "--limit", String(limit), "--json"])
    : requestAriApiSync<{
        memories: Array<{
          id: string;
          type: MemoryType;
          title: string;
          content: string;
          tags: string[];
          created_at: string;
          updated_at: string;
        }>;
      }>("GET", "/memory", {
        query: { limit, types }
      });
  return payload.memories.map(parseCanonicalMemory);
}

export function searchCanonicalMemories(query: string, limit = 20, types: MemoryType[] = []): MemoryRecord[] {
  const payload = isSubprocessBridgeMode()
    ? runCanonicalJsonCommand<{
        memories: Array<{
          id: string;
          type: MemoryType;
          title: string;
          content: string;
          tags: string[];
          created_at: string;
          updated_at: string;
        }>;
      }>(["api", "memory", "search", "--query", query, ...types.flatMap((type) => ["--type", type]), "--limit", String(limit), "--json"])
    : requestAriApiSync<{
        memories: Array<{
          id: string;
          type: MemoryType;
          title: string;
          content: string;
          tags: string[];
          created_at: string;
          updated_at: string;
        }>;
      }>("GET", "/memory", {
        query: { query, limit, types }
      });
  return payload.memories.map(parseCanonicalMemory);
}
