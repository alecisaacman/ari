import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { stopBackgroundRuntime } from "../src/core/agent/background-runtime";
import { closeDatabase } from "../src/core/db/database";
import { resetModelProvider } from "../src/core/models";

const TESTS_DIR = path.dirname(fileURLToPath(import.meta.url));
const CANONICAL_ARI_PROJECT_ROOT = path.resolve(TESTS_DIR, "..", "..", "..");

export function setupIsolatedRuntime(name: string, mode: "manual" | "assisted" | "auto" = "manual"): string {
  stopBackgroundRuntime();
  closeDatabase();
  resetModelProvider();

  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), `ari-system-${name}-`));
  fs.mkdirSync(path.join(tempRoot, "runtime"), { recursive: true });
  fs.mkdirSync(path.join(tempRoot, "workspace"), { recursive: true });

  process.chdir(tempRoot);
  process.env.ARI_UI_PASSWORD = "test-password";
  process.env.ARI_TRIGGER_TOKEN = "test-trigger";
  process.env.ARI_AUTH_SECRET = "test-secret";
  process.env.ARI_CANONICAL_PROJECT_ROOT = CANONICAL_ARI_PROJECT_ROOT;
  process.env.ARI_CANONICAL_HOME = path.join(tempRoot, "ari-home");
  process.env.ARI_CANONICAL_PYTHON = "python3.12";
  process.env.ARI_ORCHESTRATION_MODE = mode;
  process.env.ARI_EXECUTION_STALL_MINUTES = "60";
  delete process.env.ARI_OPENAI_API_KEY;

  return tempRoot;
}

export function teardownIsolatedRuntime(): void {
  stopBackgroundRuntime();
  closeDatabase();
  resetModelProvider();
}

export function writeBuilderDrop(tempRoot: string, filename: string, contents: string): string {
  const inboxRoot = path.join(tempRoot, "runtime", "orchestration", "inbox");
  fs.mkdirSync(inboxRoot, { recursive: true });
  const filePath = path.join(inboxRoot, filename);
  fs.writeFileSync(filePath, contents, "utf8");
  return filePath;
}

export function writeBuilderDropJson(
  tempRoot: string,
  filename: string,
  payload: {
    rawOutput: string;
    source?: string;
    parentOrchestrationId?: string;
    linkedImprovementIds?: string[];
    verificationSignal?: "completed" | "verified";
  }
): string {
  const inboxRoot = path.join(tempRoot, "runtime", "orchestration", "inbox");
  fs.mkdirSync(inboxRoot, { recursive: true });
  const filePath = path.join(inboxRoot, filename);
  fs.writeFileSync(filePath, `${JSON.stringify(payload, null, 2)}\n`, "utf8");
  return filePath;
}

export function readOutboxJson(tempRoot: string, filename: string): Record<string, unknown> {
  const filePath = path.join(tempRoot, "runtime", "orchestration", "outbox", filename);
  return JSON.parse(fs.readFileSync(filePath, "utf8")) as Record<string, unknown>;
}

export function readDispatchJson(tempRoot: string, filename: string): Record<string, unknown> {
  const filePath = path.join(tempRoot, "runtime", "orchestration", "dispatch", filename);
  return JSON.parse(fs.readFileSync(filePath, "utf8")) as Record<string, unknown>;
}

export function readConsumedJson(tempRoot: string, filename: string): Record<string, unknown> {
  const filePath = path.join(tempRoot, "runtime", "orchestration", "dispatch-consumed", filename);
  return JSON.parse(fs.readFileSync(filePath, "utf8")) as Record<string, unknown>;
}

export function readDispatchConsumerLog(tempRoot: string): Array<Record<string, unknown>> {
  const filePath = path.join(tempRoot, "runtime", "orchestration", "dispatch-consumer.log");
  if (!fs.existsSync(filePath)) {
    return [];
  }

  return fs
    .readFileSync(filePath, "utf8")
    .trim()
    .split("\n")
    .filter(Boolean)
    .map((line) => {
      const start = line.indexOf("{");
      if (start === -1) {
        return null;
      }
      try {
        return JSON.parse(line.slice(start)) as Record<string, unknown>;
      } catch {
        return null;
      }
    })
    .filter((value): value is Record<string, unknown> => value !== null);
}
