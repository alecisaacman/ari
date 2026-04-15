import { execFileSync } from "node:child_process";

import { getConfig } from "@/src/core/config";

export type CoordinationEntity =
  | "project"
  | "project_milestone"
  | "project_step"
  | "orchestration_record"
  | "self_improvement"
  | "dispatch_record"
  | "execution_outcome";

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

export function putCanonicalCoordinationRecord<T extends Record<string, unknown>>(entity: CoordinationEntity, payload: T): T {
  const stdout = runCanonicalCommand(["api", "coordination", "put", "--entity", entity, "--payload-json", JSON.stringify(payload)]);
  return JSON.parse(stdout) as T;
}

export function getCanonicalCoordinationRecord<T extends Record<string, unknown>>(entity: CoordinationEntity, id: string): T | null {
  const stdout = runCanonicalCommand(["api", "coordination", "get", "--entity", entity, "--id", id]);
  const payload = JSON.parse(stdout) as T | { record: null };
  if ("record" in payload) {
    return null;
  }
  return payload;
}

export function listCanonicalCoordinationRecords<T extends Record<string, unknown>>(entity: CoordinationEntity, limit = 50): T[] {
  const stdout = runCanonicalCommand(["api", "coordination", "list", "--entity", entity, "--limit", String(limit)]);
  const payload = JSON.parse(stdout) as { records: T[] };
  return payload.records;
}
