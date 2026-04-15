import type { TaskRecord } from "@/src/core/memory/types";
import { AriApiError, isSubprocessBridgeMode, requestAriApiSync, runCanonicalJsonCommand } from "@/src/core/ari-spine/api-client";

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
  const payload = isSubprocessBridgeMode()
    ? runCanonicalJsonCommand<{
        id: number;
        title: string;
        status: "open" | "done";
        notes: string;
        created_at: string;
        updated_at: string;
      }>(["api", "tasks", "create", "--title", title, "--notes", notes, "--json"])
    : requestAriApiSync<{
        id: number;
        title: string;
        status: "open" | "done";
        notes: string;
        created_at: string;
        updated_at: string;
      }>("POST", "/tasks", {
        body: { title, notes }
      });
  return parseCanonicalTask(payload);
}

export function listCanonicalTasks(limit = 20): TaskRecord[] {
  const payload = isSubprocessBridgeMode()
    ? runCanonicalJsonCommand<{
        tasks: Array<{
          id: number;
          title: string;
          status: "open" | "done";
          notes: string;
          created_at: string;
          updated_at: string;
        }>;
      }>(["api", "tasks", "list", "--limit", String(limit), "--json"])
    : requestAriApiSync<{
        tasks: Array<{
          id: number;
          title: string;
          status: "open" | "done";
          notes: string;
          created_at: string;
          updated_at: string;
        }>;
      }>("GET", "/tasks", {
        query: { limit }
      });
  return payload.tasks.map(parseCanonicalTask);
}

export function getCanonicalTaskById(id: string): TaskRecord | null {
  try {
    if (isSubprocessBridgeMode()) {
      const payload = runCanonicalJsonCommand<{
        task?: {
          id: number;
          title: string;
          status: "open" | "done";
          notes: string;
          created_at: string;
          updated_at: string;
        } | null;
      }>(["api", "tasks", "get", "--id", id, "--json"]);
      return payload.task ? parseCanonicalTask(payload.task) : null;
    }

    const payload = requestAriApiSync<{
      id: number;
      title: string;
      status: "open" | "done";
      notes: string;
      created_at: string;
      updated_at: string;
    }>("GET", `/tasks/${id}`);
    return parseCanonicalTask(payload);
  } catch (error) {
    if (error instanceof AriApiError && error.status === 404) {
      return null;
    }
    if (error instanceof Error && /not found|404/i.test(error.message)) {
      return null;
    }
    return null;
  }
}

export function searchCanonicalTasks(query: string, limit = 10): TaskRecord[] {
  const payload = isSubprocessBridgeMode()
    ? runCanonicalJsonCommand<{
        tasks: Array<{
          id: number;
          title: string;
          status: "open" | "done";
          notes: string;
          created_at: string;
          updated_at: string;
        }>;
      }>(["api", "tasks", "search", "--query", query, "--limit", String(limit), "--json"])
    : requestAriApiSync<{
        tasks: Array<{
          id: number;
          title: string;
          status: "open" | "done";
          notes: string;
          created_at: string;
          updated_at: string;
        }>;
      }>("GET", "/tasks", {
        query: { query, limit }
      });
  return payload.tasks.map(parseCanonicalTask);
}
