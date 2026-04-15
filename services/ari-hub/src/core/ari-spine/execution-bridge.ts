import { isSubprocessBridgeMode, requestAriApi, requestAriApiSync, runCanonicalJsonCommand } from "@/src/core/ari-spine/api-client";
import type { CodingActionRecord, CodingExecutionSnapshot, CodingOperation, CommandRunRecord, FileMutationRecord } from "@/src/core/memory/types";

function parseCodingAction(payload: {
  id: string;
  title: string;
  summary: string;
  status: CodingActionRecord["status"];
  approval_required: boolean;
  risky: boolean;
  target_paths: string[];
  operations: CodingOperation[];
  verify_command: string;
  working_directory: string;
  current_step: string;
  last_command_run_id?: string | null;
  last_command_summary: string;
  result_summary: string;
  retryable: boolean;
  blocked_reason?: string | null;
  created_at: string;
  approved_at?: string | null;
  applied_at?: string | null;
  tested_at?: string | null;
  passed_at?: string | null;
  failed_at?: string | null;
  verified_at?: string | null;
  updated_at: string;
}): CodingActionRecord {
  return {
    id: payload.id,
    title: payload.title,
    summary: payload.summary,
    status: payload.status,
    approvalRequired: payload.approval_required,
    risky: payload.risky,
    targetPaths: payload.target_paths || [],
    operations: payload.operations || [],
    verifyCommand: payload.verify_command,
    workingDirectory: payload.working_directory,
    currentStep: payload.current_step,
    lastCommandRunId: payload.last_command_run_id || undefined,
    lastCommandSummary: payload.last_command_summary,
    resultSummary: payload.result_summary,
    retryable: payload.retryable,
    blockedReason: payload.blocked_reason || undefined,
    createdAt: payload.created_at,
    approvedAt: payload.approved_at || undefined,
    appliedAt: payload.applied_at || undefined,
    testedAt: payload.tested_at || undefined,
    passedAt: payload.passed_at || undefined,
    failedAt: payload.failed_at || undefined,
    verifiedAt: payload.verified_at || undefined,
    updatedAt: payload.updated_at
  };
}

function parseCommandRun(payload: {
  id: string;
  action_id: string;
  command: string;
  cwd: string;
  success: boolean;
  exit_code: number;
  timed_out: boolean;
  retryable: boolean;
  stdout: string;
  stderr: string;
  classification: CommandRunRecord["classification"];
  created_at: string;
} | null): CommandRunRecord | null {
  if (!payload) {
    return null;
  }
  return {
    id: payload.id,
    actionId: payload.action_id,
    command: payload.command,
    cwd: payload.cwd,
    success: payload.success,
    exitCode: payload.exit_code,
    timedOut: payload.timed_out,
    retryable: payload.retryable,
    stdout: payload.stdout,
    stderr: payload.stderr,
    classification: payload.classification,
    createdAt: payload.created_at
  };
}

function parseFileMutation(payload: {
  id: string;
  action_id?: string | null;
  path: string;
  operation: "write" | "patch";
  success: boolean;
  details: string;
  previous_sha256?: string | null;
  new_sha256?: string | null;
  created_at: string;
} | null): FileMutationRecord | null {
  if (!payload) {
    return null;
  }
  return {
    id: payload.id,
    actionId: payload.action_id || undefined,
    path: payload.path,
    operation: payload.operation,
    success: payload.success,
    details: payload.details,
    previousSha256: payload.previous_sha256 || undefined,
    newSha256: payload.new_sha256 || undefined,
    createdAt: payload.created_at
  };
}

export async function createCanonicalCodingAction(payload: {
  title: string;
  summary?: string;
  operations: CodingOperation[];
  verifyCommand?: string;
  workingDirectory?: string;
  approvalRequired?: boolean | null;
}): Promise<CodingActionRecord> {
  if (isSubprocessBridgeMode()) {
    const created = runCanonicalJsonCommand<{ action: ReturnType<typeof parseCodingAction> }>([
      "api",
      "execution",
      "actions",
      "create",
      "--title",
      payload.title,
      "--summary",
      payload.summary || "",
      "--operations-json",
      JSON.stringify(payload.operations),
      "--verify-command",
      payload.verifyCommand || "",
      "--working-directory",
      payload.workingDirectory || ".",
      "--approval-required",
      payload.approvalRequired == null ? "auto" : payload.approvalRequired ? "true" : "false"
    ]);
    return parseCodingAction(created.action as any);
  }

  const created = await requestAriApi<{ action: any }>("POST", "/execution/actions", {
    body: payload
  });
  return parseCodingAction(created.action);
}

export async function approveCanonicalCodingAction(actionId: string): Promise<CodingActionRecord> {
  if (isSubprocessBridgeMode()) {
    const approved = runCanonicalJsonCommand<{ action: any }>(["api", "execution", "actions", "approve", "--id", actionId]);
    return parseCodingAction(approved.action);
  }

  const approved = await requestAriApi<{ action: any }>("POST", `/execution/actions/${actionId}/approve`);
  return parseCodingAction(approved.action);
}

export async function runCanonicalCodingAction(actionId: string): Promise<{
  action: CodingActionRecord;
  commandRun: CommandRunRecord | null;
  lastMutation: FileMutationRecord | null;
}> {
  if (isSubprocessBridgeMode()) {
    const executed = runCanonicalJsonCommand<{ action: any; command_run?: any; mutations?: any[] }>([
      "api",
      "execution",
      "actions",
      "run",
      "--id",
      actionId
    ]);
    return {
      action: parseCodingAction(executed.action),
      commandRun: parseCommandRun(executed.command_run || null),
      lastMutation: parseFileMutation(executed.mutations?.[executed.mutations.length - 1] || null)
    };
  }

  const executed = await requestAriApi<{ action: any; command_run?: any; mutations?: any[] }>("POST", `/execution/actions/${actionId}/run`);
  return {
    action: parseCodingAction(executed.action),
    commandRun: parseCommandRun(executed.command_run || null),
    lastMutation: parseFileMutation(executed.mutations?.[executed.mutations.length - 1] || null)
  };
}

export function getCanonicalCodingExecutionSnapshot(): CodingExecutionSnapshot {
  const payload = isSubprocessBridgeMode()
    ? runCanonicalJsonCommand<{
        current_action: any | null;
        recent_actions: any[];
        last_command_run: any | null;
        last_file_mutation: any | null;
      }>(["api", "execution", "snapshot", "--limit", "6"])
    : requestAriApiSync<{
        current_action: any | null;
        recent_actions: any[];
        last_command_run: any | null;
        last_file_mutation: any | null;
      }>("GET", "/execution/snapshot", {
        query: { limit: 6 }
      });

  return {
    currentAction: payload.current_action ? parseCodingAction(payload.current_action) : null,
    recentActions: (payload.recent_actions || []).map(parseCodingAction),
    lastCommandRun: parseCommandRun(payload.last_command_run || null),
    lastFileMutation: parseFileMutation(payload.last_file_mutation || null)
  };
}
