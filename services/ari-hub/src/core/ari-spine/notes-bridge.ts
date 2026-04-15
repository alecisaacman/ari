import { isSubprocessBridgeMode, requestAriApi, runCanonicalJsonCommand } from "@/src/core/ari-spine/api-client";

export type CanonicalNote = {
  id: string;
  title: string;
  content: string;
  createdAt: string;
  updatedAt: string;
};

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
  const payload = isSubprocessBridgeMode()
    ? runCanonicalJsonCommand<{
        id: number;
        title: string;
        content: string;
        created_at: string;
        updated_at: string;
      }>(["api", "notes", "save", "--title", title, "--body", content, "--json"])
    : await requestAriApi<{
        id: number;
        title: string;
        content: string;
        created_at: string;
        updated_at: string;
      }>("POST", "/notes", {
        body: { title, content }
      });

  return parseCanonicalNote(payload);
}

export async function searchCanonicalNotes(query: string, limit = 10): Promise<CanonicalNote[]> {
  const payload = isSubprocessBridgeMode()
    ? runCanonicalJsonCommand<{
        notes: Array<{
          id: number;
          title: string;
          content: string;
          created_at: string;
          updated_at: string;
        }>;
      }>(["api", "notes", "search", "--query", query, "--limit", String(limit), "--json"])
    : await requestAriApi<{
        notes: Array<{
          id: number;
          title: string;
          content: string;
          created_at: string;
          updated_at: string;
        }>;
      }>("GET", "/notes", {
        query: { query, limit }
      });
  return payload.notes.map(parseCanonicalNote);
}
