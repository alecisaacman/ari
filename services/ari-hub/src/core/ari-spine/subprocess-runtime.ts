import { execFileSync } from "node:child_process";
import path from "node:path";

import { getConfig } from "@/src/core/config";

// Legacy fallback only. The hub should use ari-api by default.
export function runCanonicalSubprocessCommand(args: string[]): string {
  const config = getConfig();
  const pythonPath = path.join(config.canonicalAriProjectRoot, "services", "ari-core", "src");

  return execFileSync(config.canonicalPythonCommand, ["-m", "ari_core.ari", ...args], {
    cwd: config.canonicalAriProjectRoot,
    env: {
      ...process.env,
      PYTHONPATH: [pythonPath, process.env.PYTHONPATH].filter(Boolean).join(path.delimiter),
      ...(config.canonicalAriHome ? { ARI_HOME: config.canonicalAriHome } : {})
    },
    encoding: "utf8"
  }).trim();
}
