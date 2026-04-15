import fs from "node:fs";
import path from "node:path";

import { getConfig } from "@/src/core/config";

function normalizeRelativePath(inputPath: string): string {
  return inputPath.replace(/^\/+/, "");
}

export function resolveWorkspacePath(inputPath: string): string {
  const config = getConfig();
  const candidate = path.resolve(config.workspaceRoot, normalizeRelativePath(inputPath));
  const workspaceRoot = path.resolve(config.workspaceRoot);

  if (candidate !== workspaceRoot && !candidate.startsWith(`${workspaceRoot}${path.sep}`)) {
    throw new Error("Path escapes the ARI workspace sandbox.");
  }

  return candidate;
}

export function listWorkspaceFiles(relativePath = "."): { path: string; kind: "file" | "directory" }[] {
  const targetPath = resolveWorkspacePath(relativePath);
  return fs.readdirSync(targetPath, { withFileTypes: true }).map((entry) => ({
    path: path.relative(getConfig().workspaceRoot, path.join(targetPath, entry.name)) || ".",
    kind: entry.isDirectory() ? "directory" : "file"
  }));
}

export function readWorkspaceFile(relativePath: string): string {
  return fs.readFileSync(resolveWorkspacePath(relativePath), "utf8");
}

export function writeWorkspaceFile(relativePath: string, content: string): string {
  const filePath = resolveWorkspacePath(relativePath);
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, content, "utf8");
  return path.relative(getConfig().workspaceRoot, filePath);
}
