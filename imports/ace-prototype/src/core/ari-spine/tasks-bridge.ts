import { execFileSync } from "node:child_process";

import { getConfig } from "@/src/core/config";
import type { TaskRecord } from "@/src/core/memory/types";

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

function parseCanonicalTask(payload: {
  id: number;
  title: string;
  status: "open" | "done";
  notes: string;
  created_at: string;
  updated_at: string;
}): TaskRecord {
  return {
    id: String(payload.id),
    title: payload.title,
    status: payload.status,
    notes: payload.notes,
    createdAt: payload.created_at,
    updatedAt: payload.updated_at
  };
}

export function createCanonicalTask(title: string, notes = ""): TaskRecord {
  const stdout = runCanonicalCommand(["api", "tasks", "create", "--title", title, "--notes", notes, "--json"]);
  return parseCanonicalTask(
    JSON.parse(stdout) as {
      id: number;
      title: string;
      status: "open" | "done";
      notes: string;
      created_at: string;
      updated_at: string;
    }
  );
}

export function listCanonicalTasks(limit = 20): TaskRecord[] {
  const stdout = runCanonicalCommand(["api", "tasks", "list", "--limit", String(limit), "--json"]);
  const payload = JSON.parse(stdout) as {
    tasks: Array<{
      id: number;
      title: string;
      status: "open" | "done";
      notes: string;
      created_at: string;
      updated_at: string;
    }>;
  };
  return payload.tasks.map(parseCanonicalTask);
}

export function getCanonicalTaskById(id: string): TaskRecord | null {
  const stdout = runCanonicalCommand(["api", "tasks", "get", "--id", id, "--json"]);
  const payload = JSON.parse(stdout) as
    | {
        id: number;
        title: string;
        status: "open" | "done";
        notes: string;
        created_at: string;
        updated_at: string;
      }
    | { task: null };

  if ("task" in payload) {
    return null;
  }

  return parseCanonicalTask(payload);
}

export function searchCanonicalTasks(query: string, limit = 10): TaskRecord[] {
  const stdout = runCanonicalCommand(["api", "tasks", "search", "--query", query, "--limit", String(limit), "--json"]);
  const payload = JSON.parse(stdout) as {
    tasks: Array<{
      id: number;
      title: string;
      status: "open" | "done";
      notes: string;
      created_at: string;
      updated_at: string;
    }>;
  };
  return payload.tasks.map(parseCanonicalTask);
}
