export type ToolStatus = "ok" | "error";

export type ToolResult = {
  tool: string;
  status: ToolStatus;
  summary: string;
  data?: unknown;
};

export type ToolDefinition<TInput = unknown> = {
  name: string;
  description: string;
  validate(input: unknown): TInput;
  execute(input: TInput): Promise<ToolResult>;
};
