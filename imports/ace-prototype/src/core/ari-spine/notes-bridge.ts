import { execFile } from "node:child_process";
import path from "node:path";
import { promisify } from "node:util";

import { getConfig } from "@/src/core/config";

const execFileAsync = promisify(execFile);

export type CanonicalNote = {
  id: string;
  title: string;
  content: string;
  createdAt: string;
  updatedAt: string;
};

function buildCommandEnvironment(): NodeJS.ProcessEnv {
  const config = getConfig();
  return {
    ...process.env,
    PYTHONPATH: "src",
    ...(config.canonicalAriHome ? { ARI_HOME: config.canonicalAriHome } : {})
  };
}

async function runCanonicalCommand(args: string[]): Promise<string> {
  const config = getConfig();
  const result = await execFileAsync(config.canonicalPythonCommand, ["-m", "networking_crm.ari", ...args], {
    cwd: config.canonicalAriProjectRoot,
    env: buildCommandEnvironment()
  });
  return result.stdout.trim();
}

function parseCanonicalNote(payload: {
  id: number;
  title: string;
  content: string;
  created_at: string;
  updated_at: string;
}): CanonicalNote {
  return {
    id: String(payload.id),
    title: payload.title,
    content: payload.content,
    createdAt: payload.created_at,
    updatedAt: payload.updated_at
  };
}

export async function saveCanonicalNote(title: string, content: string): Promise<CanonicalNote> {
  const stdout = await runCanonicalCommand(["api", "notes", "save", "--title", title, "--body", content, "--json"]);
  return parseCanonicalNote(JSON.parse(stdout) as {
    id: number;
    title: string;
    content: string;
    created_at: string;
    updated_at: string;
  });
}

export async function searchCanonicalNotes(query: string, limit = 10): Promise<CanonicalNote[]> {
  const stdout = await runCanonicalCommand(["api", "notes", "search", "--query", query, "--limit", String(limit), "--json"]);
  const payload = JSON.parse(stdout) as {
    notes: Array<{
      id: number;
      title: string;
      content: string;
      created_at: string;
      updated_at: string;
    }>;
  };
  return payload.notes.map(parseCanonicalNote);
}
