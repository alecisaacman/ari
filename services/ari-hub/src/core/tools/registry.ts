import { saveCanonicalNote, searchCanonicalNotes } from "@/src/core/ari-spine/notes-bridge";
import { createTask, listTasks, logToolRun, retrieveMemories, saveMemory } from "@/src/core/memory/repository";
import type { ToolDefinition, ToolResult } from "@/src/core/tools/types";
import { listWorkspaceFiles, readWorkspaceFile, writeWorkspaceFile } from "@/src/core/tools/workspace";

function expectRecord(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("Tool input must be an object.");
  }
  return value as Record<string, unknown>;
}

function expectString(value: unknown, fieldName: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${fieldName} must be a non-empty string.`);
  }
  return value.trim();
}

function defineTool<TInput>(tool: ToolDefinition<TInput>): ToolDefinition<TInput> {
  return tool;
}

const toolDefinitions = [
  defineTool({
    name: "save_note",
    description: "Save a note to persistent memory.",
    validate(input) {
      const record = expectRecord(input);
      return {
        title: expectString(record.title, "title"),
        content: expectString(record.content, "content")
      };
    },
    async execute(input: { title: string; content: string }) {
      const memory = await saveCanonicalNote(input.title, input.content);
      return {
        tool: "save_note",
        status: "ok",
        summary: `Saved note "${memory.title}".`,
        data: memory
      };
    }
  }),
  defineTool({
    name: "retrieve_notes",
    description: "Retrieve saved notes using keyword search.",
    validate(input) {
      const record = expectRecord(input);
      return {
        query: typeof record.query === "string" ? record.query : ""
      };
    },
    async execute(input: { query: string }) {
      const matches = await searchCanonicalNotes(input.query);
      return {
        tool: "retrieve_notes",
        status: "ok",
        summary: matches.length ? `Found ${matches.length} matching note(s).` : "No matching notes found.",
        data: matches
      };
    }
  }),
  defineTool({
    name: "create_task",
    description: "Create a persistent task.",
    validate(input) {
      const record = expectRecord(input);
      return {
        title: expectString(record.title, "title"),
        notes: typeof record.notes === "string" ? record.notes : ""
      };
    },
    async execute(input: { title: string; notes: string }) {
      const task = createTask(input.title, input.notes);
      return {
        tool: "create_task",
        status: "ok",
        summary: `Created task "${task.title}".`,
        data: task
      };
    }
  }),
  defineTool({
    name: "list_tasks",
    description: "List active tasks.",
    validate() {
      return {};
    },
    async execute() {
      const tasks = listTasks();
      return {
        tool: "list_tasks",
        status: "ok",
        summary: tasks.length ? `Loaded ${tasks.length} task(s).` : "No tasks found.",
        data: tasks
      };
    }
  }),
  defineTool({
    name: "list_files",
    description: "List files inside the ARI workspace.",
    validate(input) {
      const record = expectRecord(input);
      return {
        path: typeof record.path === "string" ? record.path : "."
      };
    },
    async execute(input: { path: string }) {
      const entries = listWorkspaceFiles(input.path);
      return {
        tool: "list_files",
        status: "ok",
        summary: `Listed ${entries.length} entr${entries.length === 1 ? "y" : "ies"} in workspace.`,
        data: entries
      };
    }
  }),
  defineTool({
    name: "read_file",
    description: "Read a file inside the ARI workspace.",
    validate(input) {
      const record = expectRecord(input);
      return {
        path: expectString(record.path, "path")
      };
    },
    async execute(input: { path: string }) {
      const content = readWorkspaceFile(input.path);
      return {
        tool: "read_file",
        status: "ok",
        summary: `Read ${input.path}.`,
        data: { path: input.path, content }
      };
    }
  }),
  defineTool({
    name: "write_file",
    description: "Write a file inside the ARI workspace.",
    validate(input) {
      const record = expectRecord(input);
      return {
        path: expectString(record.path, "path"),
        content: typeof record.content === "string" ? record.content : ""
      };
    },
    async execute(input: { path: string; content: string }) {
      const savedPath = writeWorkspaceFile(input.path, input.content);
      return {
        tool: "write_file",
        status: "ok",
        summary: `Wrote ${savedPath}.`,
        data: { path: savedPath }
      };
    }
  })
];

export function getToolDefinitions(): ToolDefinition[] {
  return toolDefinitions;
}

export async function runTool(name: string, input: unknown): Promise<ToolResult> {
  const tool = toolDefinitions.find((candidate) => candidate.name === name);
  if (!tool) {
    const result = {
      tool: name,
      status: "error" as const,
      summary: `Unknown tool: ${name}.`
    };
    logToolRun(name, result.status, input, result);
    return result;
  }

  try {
    const validatedInput = tool.validate(input);
    const result = await tool.execute(validatedInput);
    logToolRun(tool.name, result.status, input, result);
    return result;
  } catch (error) {
    const result = {
      tool: name,
      status: "error" as const,
      summary: error instanceof Error ? error.message : "Tool execution failed."
    };
    logToolRun(name, result.status, input, result);
    return result;
  }
}
