import { spawnSync } from "node:child_process";

import { getConfig } from "@/src/core/config";
import { runCanonicalSubprocessCommand } from "@/src/core/ari-spine/subprocess-runtime";

type RequestOptions = {
  query?: Record<string, string | number | boolean | Array<string | number | boolean> | undefined>;
  body?: unknown;
};

type WorkerResult = {
  ok: boolean;
  status?: number;
  body?: string;
  error?: string;
};

export class AriApiError extends Error {
  readonly status?: number;
  readonly details?: unknown;

  constructor(message: string, options: { status?: number; details?: unknown } = {}) {
    super(message);
    this.name = "AriApiError";
    this.status = options.status;
    this.details = options.details;
  }
}

export function isSubprocessBridgeMode(): boolean {
  return getConfig().canonicalBridgeMode === "subprocess";
}

function buildUrl(pathname: string, query?: RequestOptions["query"]): string {
  const config = getConfig();
  const url = new URL(pathname, config.canonicalApiBaseUrl);

  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value === undefined) {
        continue;
      }
      if (Array.isArray(value)) {
        for (const item of value) {
          url.searchParams.append(key, String(item));
        }
      } else {
        url.searchParams.set(key, String(value));
      }
    }
  }

  return url.toString();
}

export async function requestAriApi<T>(method: "GET" | "POST" | "PUT", pathname: string, options: RequestOptions = {}): Promise<T> {
  const config = getConfig();
  const response = await fetch(buildUrl(pathname, options.query), {
    method,
    headers: {
      Accept: "application/json",
      ...(options.body !== undefined ? { "Content-Type": "application/json" } : {})
    },
    body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
    signal: AbortSignal.timeout(config.canonicalApiTimeoutMs)
  });

  const text = await response.text();
  const parsed = safeParseJson(text);

  if (!response.ok) {
    throw new AriApiError(`ari-api ${method} ${pathname} failed with ${response.status}.`, {
      status: response.status,
      details: parsed ?? text
    });
  }

  return parsed as T;
}

export function requestAriApiSync<T>(method: "GET" | "POST" | "PUT", pathname: string, options: RequestOptions = {}): T {
  const config = getConfig();
  if (isSubprocessBridgeMode()) {
    throw new AriApiError("Synchronous ari-api calls are unavailable in subprocess bridge mode.");
  }

  const result = spawnSync(
    process.execPath,
    [
      "-e",
      `
        const payload = JSON.parse(process.argv[1]);
        (async () => {
          try {
            const response = await fetch(payload.url, {
              method: payload.method,
              headers: payload.headers,
              body: payload.body,
              signal: AbortSignal.timeout(payload.timeoutMs)
            });
            const body = await response.text();
            process.stdout.write(JSON.stringify({ ok: response.ok, status: response.status, body }));
          } catch (error) {
            process.stdout.write(
              JSON.stringify({
                ok: false,
                error: error instanceof Error ? error.message : String(error)
              })
            );
          }
        })();
      `,
      JSON.stringify({
        method,
        url: buildUrl(pathname, options.query),
        headers: {
          Accept: "application/json",
          ...(options.body !== undefined ? { "Content-Type": "application/json" } : {})
        },
        body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
        timeoutMs: config.canonicalApiTimeoutMs
      })
    ],
    {
      encoding: "utf8",
      timeout: config.canonicalApiTimeoutMs + 500
    }
  );

  if (result.error) {
    throw new AriApiError(`ari-api ${method} ${pathname} failed before a response was received.`, {
      details: result.error
    });
  }

  if (result.status !== 0) {
    throw new AriApiError(`ari-api ${method} ${pathname} exited with status ${result.status}.`, {
      details: result.stderr
    });
  }

  const settledResult = safeParseJson(result.stdout) as WorkerResult | null;
  if (!settledResult) {
    throw new AriApiError(`ari-api ${method} ${pathname} returned no result.`, {
      details: result.stdout
    });
  }

  if (!settledResult.ok) {
    throw new AriApiError(`ari-api ${method} ${pathname} failed${settledResult.status ? ` with ${settledResult.status}` : ""}.`, {
      status: settledResult.status,
      details: settledResult.body ? safeParseJson(settledResult.body) ?? settledResult.body : settledResult.error
    });
  }

  return safeParseJson(settledResult.body ?? "") as T;
}

export function runCanonicalCommand(args: string[]): string {
  if (isSubprocessBridgeMode()) {
    return runCanonicalSubprocessCommand(args);
  }

  throw new AriApiError(
    "Direct canonical subprocess commands are disabled in API bridge mode. Use ari-api bridge helpers instead."
  );
}

export function runCanonicalJsonCommand<T>(args: string[]): T {
  const raw = runCanonicalCommand(args);
  const parsed = safeParseJson(raw);

  if (parsed === null) {
    throw new AriApiError("Canonical subprocess command did not return JSON.", {
      details: raw
    });
  }

  return parsed as T;
}

function safeParseJson(text: string): unknown {
  if (!text.trim()) {
    return null;
  }

  try {
    return JSON.parse(text) as unknown;
  } catch {
    return null;
  }
}
