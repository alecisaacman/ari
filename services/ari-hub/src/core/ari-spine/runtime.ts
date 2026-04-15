import { execFileSync } from "node:child_process";
import path from "node:path";

import { getConfig } from "@/src/core/config";

export function buildCanonicalCommandEnvironment(): NodeJS.ProcessEnv {
  const config = getConfig();
  const pythonPath = path.join(config.canonicalAriProjectRoot, "services", "ari-core", "src");

  return {
    ...process.env,
    PYTHONPATH: [pythonPath, process.env.PYTHONPATH].filter(Boolean).join(path.delimiter),
    ...(config.canonicalAriHome ? { ARI_HOME: config.canonicalAriHome } : {})
  };
}

export function runCanonicalCommand(args: string[]): string {
  const config = getConfig();
  return execFileSync(config.canonicalPythonCommand, ["-m", "ari_core.ari", ...args], {
    cwd: config.canonicalAriProjectRoot,
    env: buildCanonicalCommandEnvironment(),
    encoding: "utf8"
  }).trim();
}
