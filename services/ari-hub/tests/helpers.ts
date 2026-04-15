import { spawn, type ChildProcess } from "node:child_process";
import fs from "node:fs";
import net from "node:net";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { stopBackgroundRuntime } from "../src/core/agent/background-runtime";
import { closeDatabase } from "../src/core/db/database";
import { resetModelProvider } from "../src/core/models";

const TESTS_DIR = path.dirname(fileURLToPath(import.meta.url));
const CANONICAL_ARI_PROJECT_ROOT = path.resolve(TESTS_DIR, "..", "..", "..");
const CANONICAL_ARI_VENV_PYTHON = path.join(CANONICAL_ARI_PROJECT_ROOT, ".venv312", "bin", "python");
let apiServerProcess: ChildProcess | null = null;

export function setupIsolatedRuntime(name: string, mode: "manual" | "assisted" | "auto" = "manual"): string {
  stopBackgroundRuntime();
  closeDatabase();
  resetModelProvider();

  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), `ari-system-${name}-`));
  fs.mkdirSync(path.join(tempRoot, "runtime"), { recursive: true });
  fs.mkdirSync(path.join(tempRoot, "workspace"), { recursive: true });
  fs.mkdirSync(path.join(tempRoot, "execution-root"), { recursive: true });

  process.chdir(tempRoot);
  process.env.ARI_UI_PASSWORD = "test-password";
  process.env.ARI_TRIGGER_TOKEN = "test-trigger";
  process.env.ARI_AUTH_SECRET = "test-secret";
  process.env.ARI_CANONICAL_PROJECT_ROOT = CANONICAL_ARI_PROJECT_ROOT;
  process.env.ARI_CANONICAL_HOME = path.join(tempRoot, "ari-home");
  process.env.ARI_EXECUTION_ROOT = path.join(tempRoot, "execution-root");
  process.env.ARI_CANONICAL_PYTHON = CANONICAL_ARI_VENV_PYTHON;
  process.env.ARI_CANONICAL_BRIDGE_MODE = "subprocess";
  delete process.env.ARI_API_BASE_URL;
  process.env.ARI_ORCHESTRATION_MODE = mode;
  process.env.ARI_EXECUTION_STALL_MINUTES = "60";
  delete process.env.ARI_OPENAI_API_KEY;

  return tempRoot;
}

export async function setupApiBackedRuntime(
  name: string,
  mode: "manual" | "assisted" | "auto" = "manual"
): Promise<string> {
  const tempRoot = setupIsolatedRuntime(name, mode);
  const port = await reservePort();
  const pythonPath = [
    path.join(CANONICAL_ARI_PROJECT_ROOT, "services", "ari-core", "src"),
    path.join(CANONICAL_ARI_PROJECT_ROOT, "services", "ari-api", "src")
  ].join(path.delimiter);

  apiServerProcess = spawn(
    CANONICAL_ARI_VENV_PYTHON,
    ["-m", "uvicorn", "ari_api.main:app", "--host", "127.0.0.1", "--port", String(port), "--log-level", "warning"],
    {
      cwd: CANONICAL_ARI_PROJECT_ROOT,
      env: {
        ...process.env,
        PYTHONPATH: [pythonPath, process.env.PYTHONPATH].filter(Boolean).join(path.delimiter),
        ARI_HOME: path.join(tempRoot, "ari-home"),
        ARI_EXECUTION_ROOT: path.join(tempRoot, "execution-root")
      },
      stdio: "ignore"
    }
  );

  process.env.ARI_CANONICAL_BRIDGE_MODE = "api";
  process.env.ARI_API_BASE_URL = `http://127.0.0.1:${port}`;

  await waitForApi(process.env.ARI_API_BASE_URL);

  return tempRoot;
}

export function teardownIsolatedRuntime(): void {
  stopBackgroundRuntime();
  closeDatabase();
  resetModelProvider();
  if (apiServerProcess) {
    apiServerProcess.kill("SIGTERM");
    apiServerProcess = null;
  }
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

async function reservePort(): Promise<number> {
  return await new Promise<number>((resolve, reject) => {
    const server = net.createServer();
    server.unref();
    server.on("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      if (!address || typeof address === "string") {
        reject(new Error("Failed to reserve API port."));
        return;
      }
      const { port } = address;
      server.close((error) => {
        if (error) {
          reject(error);
          return;
        }
        resolve(port);
      });
    });
  });
}

async function waitForApi(baseUrl: string | undefined): Promise<void> {
  if (!baseUrl) {
    throw new Error("ARI_API_BASE_URL is required for API-backed runtime setup.");
  }

  const deadline = Date.now() + 10000;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(new URL("/health", baseUrl));
      if (response.ok) {
        return;
      }
    } catch {}
    await new Promise((resolve) => setTimeout(resolve, 100));
  }

  throw new Error(`Timed out waiting for ari-api at ${baseUrl}.`);
}
