import type { AgentDecision } from "@/src/core/agent/types";

function titleFromSentence(input: string, fallbackPrefix: string): string {
  const cleaned = input.trim().replace(/[.?!]+$/, "");
  if (!cleaned) {
    return fallbackPrefix;
  }
  return cleaned.length > 60 ? `${cleaned.slice(0, 57)}...` : cleaned;
}

export function detectIntent(message: string): AgentDecision {
  const trimmed = message.trim();

  let match = trimmed.match(/^save (?:a )?note(?: called)?\s+([^:\n]+)\s*[:\-]\s*(.+)$/i);
  if (match) {
    return {
      type: "save_memory",
      memoryType: "note",
      title: match[1].trim().replace(/^["']|["']$/g, ""),
      content: match[2].trim()
    };
  }

  match = trimmed.match(/^remember that i (prefer|like|want)\s+(.+)$/i);
  if (match) {
    const content = match[2].trim();
    return {
      type: "save_memory",
      memoryType: "preference",
      title: titleFromSentence(content, "Preference"),
      content
    };
  }

  match = trimmed.match(/^remember that\s+(.+)$/i);
  if (match) {
    const content = match[1].trim();
    return {
      type: "save_memory",
      memoryType: "fact",
      title: titleFromSentence(content, "Fact"),
      content
    };
  }

  match = trimmed.match(/^(?:plan|map|break down)\s+(?:project|goal|execution path for)\s+(.+)$/i);
  if (match) {
    return {
      type: "plan_project",
      goal: match[1].trim()
    };
  }

  match = trimmed.match(/^(find|show|retrieve|search)(?: my)? notes?(?: about| for)?\s*(.*)$/i);
  if (match) {
    return {
      type: "retrieve_notes",
      query: match[2].trim()
    };
  }

  if (/^(list|show)(?: my)? tasks$/i.test(trimmed)) {
    return { type: "list_tasks" };
  }

  match = trimmed.match(/^(create|add)\s+(?:a )?task\s+(.+)$/i);
  if (match) {
    return {
      type: "create_task",
      title: match[2].trim(),
      notes: ""
    };
  }

  match = trimmed.match(/^todo[:\s]+(.+)$/i);
  if (match) {
    return {
      type: "create_task",
      title: match[1].trim(),
      notes: ""
    };
  }

  match = trimmed.match(/^list files(?: in\s+(.+))?$/i);
  if (match) {
    return {
      type: "list_files",
      path: match[1]?.trim() || "."
    };
  }

  match = trimmed.match(/^read file\s+(.+)$/i);
  if (match) {
    return {
      type: "read_file",
      path: match[1].trim()
    };
  }

  match = trimmed.match(/^write file\s+([^\n:]+)\s*(?:::\s*|:\s*|\n)([\s\S]+)$/i);
  if (match) {
    return {
      type: "write_file",
      path: match[1].trim(),
      content: match[2]
    };
  }

  match = trimmed.match(/^delegate(?: to ([a-z0-9_-]+))?\s+(.+)$/i);
  if (match) {
    return {
      type: "delegate",
      request: {
        agent: match[1]?.trim() || "planner",
        goal: match[2].trim()
      }
    };
  }

  return { type: "conversation" };
}
