import { AriApiError, isSubprocessBridgeMode, requestAriApiSync, runCanonicalJsonCommand } from "@/src/core/ari-spine/api-client";

export type CoordinationEntity =
  | "project"
  | "project_milestone"
  | "project_step"
  | "orchestration_record"
  | "self_improvement"
  | "dispatch_record"
  | "execution_outcome";

export function putCanonicalCoordinationRecord<T extends Record<string, unknown>>(entity: CoordinationEntity, payload: T): T {
  return isSubprocessBridgeMode()
    ? runCanonicalJsonCommand<T>(["api", "coordination", "put", "--entity", entity, "--payload-json", JSON.stringify(payload)])
    : requestAriApiSync<T>("PUT", `/coordination/${entity}`, {
        body: { payload }
      });
}

export function getCanonicalCoordinationRecord<T extends Record<string, unknown>>(entity: CoordinationEntity, id: string): T | null {
  try {
    const payload = isSubprocessBridgeMode()
      ? runCanonicalJsonCommand<T | { record: null }>(["api", "coordination", "get", "--entity", entity, "--id", id])
      : requestAriApiSync<T>("GET", `/coordination/${entity}/${id}`);
    if ("record" in payload && payload.record === null) {
      return null;
    }
    return payload as T;
  } catch (error) {
    if (error instanceof AriApiError && error.status === 404) {
      return null;
    }
    return null;
  }
}

export function listCanonicalCoordinationRecords<T extends Record<string, unknown>>(entity: CoordinationEntity, limit = 50): T[] {
  const payload = isSubprocessBridgeMode()
    ? runCanonicalJsonCommand<{ records: T[] }>(["api", "coordination", "list", "--entity", entity, "--limit", String(limit)])
    : requestAriApiSync<{ records: T[] }>("GET", `/coordination/${entity}`, {
        query: { limit }
      });
  return payload.records;
}
