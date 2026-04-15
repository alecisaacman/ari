import type { MemoryRecord } from "@/src/core/memory/types";
import type { ToolResult } from "@/src/core/tools/types";

export type DelegationRequest = {
  agent: string;
  goal: string;
};

export type DelegationResult = {
  agent: string;
  status: "planned" | "completed";
  summary: string;
};

export type AgentDecision =
  | { type: "conversation" }
  | { type: "save_memory"; memoryType: "note" | "fact" | "preference"; title: string; content: string }
  | { type: "plan_project"; goal: string }
  | { type: "retrieve_notes"; query: string }
  | { type: "create_task"; title: string; notes: string }
  | { type: "list_tasks" }
  | { type: "list_files"; path: string }
  | { type: "read_file"; path: string }
  | { type: "write_file"; path: string; content: string }
  | { type: "delegate"; request: DelegationRequest };

export type TurnResult = {
  conversationId: string;
  reply: string;
  memories: Array<Pick<MemoryRecord, "id" | "type" | "title">>;
  toolActivity: ToolResult[];
  delegations: DelegationResult[];
  mode: "hosted" | "fallback";
};
