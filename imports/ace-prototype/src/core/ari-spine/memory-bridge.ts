import { execFileSync } from "node:child_process";

import { getConfig } from "@/src/core/config";
import type { MemoryRecord, MemoryType } from "@/src/core/memory/types";

export const LOCAL_MEMORY_TYPES = new Set<MemoryType>(["note", "episodic_history", "conversation_history"]);

function buildCommandEnvironment(): NodeJS.ProcessEnv {
  const config = getConfig();
  return {
    ...process.env,
    PYTHONPATH: "src",
    ...(config.canonicalAriHome ? { ARI_HOME: config.canonicalAriHome } : {})
  };
}

function runCanonicalCommand(args: string[]): string {
  const config = getConfig();
  return execFileSync(config.canonicalPythonCommand, ["-m", "networking_crm.ari", ...args], {
    cwd: config.canonicalAriProjectRoot,
    env: buildCommandEnvironment(),
    encoding: "utf8"
  }).trim();
}

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
  const stdout = runCanonicalCommand([
    "api",
    "memory",
    "remember",
    "--type",
    type,
    "--title",
    title,
    "--body",
    content,
    "--tags-json",
    JSON.stringify(tags),
    "--json"
  ]);
  return parseCanonicalMemory(
    JSON.parse(stdout) as {
      id: string;
      type: MemoryType;
      title: string;
      content: string;
      tags: string[];
      created_at: string;
      updated_at: string;
    }
  );
}

export function listCanonicalMemoriesByTypes(types: MemoryType[], limit = 20): MemoryRecord[] {
  if (!types.length) {
    return [];
  }

  const args = ["api", "memory", "list", "--limit", String(limit), "--json"];
  for (const type of types) {
    args.push("--type", type);
  }

  const stdout = runCanonicalCommand(args);
  const payload = JSON.parse(stdout) as {
    memories: Array<{
      id: string;
      type: MemoryType;
      title: string;
      content: string;
      tags: string[];
      created_at: string;
      updated_at: string;
    }>;
  };
  return payload.memories.map(parseCanonicalMemory);
}

export function searchCanonicalMemories(query: string, limit = 20, types: MemoryType[] = []): MemoryRecord[] {
  const args = ["api", "memory", "search", "--query", query, "--limit", String(limit), "--json"];
  for (const type of types) {
    args.push("--type", type);
  }
  const stdout = runCanonicalCommand(args);
  const payload = JSON.parse(stdout) as {
    memories: Array<{
      id: string;
      type: MemoryType;
      title: string;
      content: string;
      tags: string[];
      created_at: string;
      updated_at: string;
    }>;
  };
  return payload.memories.map(parseCanonicalMemory);
}
