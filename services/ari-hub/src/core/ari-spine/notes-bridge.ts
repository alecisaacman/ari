import { runCanonicalCommand as runCanonicalCommandSync } from "@/src/core/ari-spine/runtime";

export type CanonicalNote = {
  id: string;
  title: string;
  content: string;
  createdAt: string;
  updatedAt: string;
};

async function runCanonicalCommand(args: string[]): Promise<string> {
  return runCanonicalCommandSync(args);
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
