import fs from "node:fs";
import path from "node:path";
import { DatabaseSync } from "node:sqlite";

import { getConfig } from "@/src/core/config";
import { SCHEMA_SQL } from "@/src/core/db/schema";

let databaseInstance: DatabaseSync | null = null;

function ensureDirectories(): void {
  const config = getConfig();
  fs.mkdirSync(config.runtimeRoot, { recursive: true });
  fs.mkdirSync(config.workspaceRoot, { recursive: true });
  fs.mkdirSync(path.join(config.runtimeRoot, "audio"), { recursive: true });
  fs.mkdirSync(config.orchestrationRoot, { recursive: true });
  fs.mkdirSync(config.orchestrationInboxRoot, { recursive: true });
  fs.mkdirSync(config.orchestrationProcessedRoot, { recursive: true });
  fs.mkdirSync(config.orchestrationOutboxRoot, { recursive: true });
  fs.mkdirSync(config.orchestrationDispatchRoot, { recursive: true });
  fs.mkdirSync(config.orchestrationDispatchConsumedRoot, { recursive: true });
}

function listColumns(database: DatabaseSync, tableName: string): Set<string> {
  const rows = database.prepare(`PRAGMA table_info(${tableName})`).all() as Array<{ name: string }>;
  return new Set(rows.map((row) => row.name));
}

function ensureSchemaMigrations(database: DatabaseSync): void {
  const orchestrationColumns = listColumns(database, "orchestration_records");
  if (!orchestrationColumns.has("parent_orchestration_id")) {
    database.exec("ALTER TABLE orchestration_records ADD COLUMN parent_orchestration_id TEXT");
  }
  if (!orchestrationColumns.has("linked_improvement_ids_json")) {
    database.exec("ALTER TABLE orchestration_records ADD COLUMN linked_improvement_ids_json TEXT NOT NULL DEFAULT '[]'");
  }
  if (!orchestrationColumns.has("verification_signal")) {
    database.exec("ALTER TABLE orchestration_records ADD COLUMN verification_signal TEXT");
  }
  if (!orchestrationColumns.has("linkage_mode")) {
    database.exec("ALTER TABLE orchestration_records ADD COLUMN linkage_mode TEXT NOT NULL DEFAULT 'heuristic'");
  }

  const improvementColumns = listColumns(database, "self_improvements");
  if (!improvementColumns.has("instruction_orchestration_id")) {
    database.exec("ALTER TABLE self_improvements ADD COLUMN instruction_orchestration_id TEXT");
  }
  if (!improvementColumns.has("dispatch_orchestration_id")) {
    database.exec("ALTER TABLE self_improvements ADD COLUMN dispatch_orchestration_id TEXT");
  }
  if (!improvementColumns.has("dispatch_mode")) {
    database.exec("ALTER TABLE self_improvements ADD COLUMN dispatch_mode TEXT");
  }
  if (!improvementColumns.has("dispatch_evidence")) {
    database.exec("ALTER TABLE self_improvements ADD COLUMN dispatch_evidence TEXT");
  }
  if (!improvementColumns.has("consumed_at")) {
    database.exec("ALTER TABLE self_improvements ADD COLUMN consumed_at TEXT");
  }
  if (!improvementColumns.has("consumer")) {
    database.exec("ALTER TABLE self_improvements ADD COLUMN consumer TEXT");
  }
  if (!improvementColumns.has("completion_orchestration_id")) {
    database.exec("ALTER TABLE self_improvements ADD COLUMN completion_orchestration_id TEXT");
  }
  if (!improvementColumns.has("completion_evidence")) {
    database.exec("ALTER TABLE self_improvements ADD COLUMN completion_evidence TEXT");
  }
  if (!improvementColumns.has("verification_orchestration_id")) {
    database.exec("ALTER TABLE self_improvements ADD COLUMN verification_orchestration_id TEXT");
  }
  if (!improvementColumns.has("verification_evidence")) {
    database.exec("ALTER TABLE self_improvements ADD COLUMN verification_evidence TEXT");
  }
  if (!improvementColumns.has("dispatch_record_id")) {
    database.exec("ALTER TABLE self_improvements ADD COLUMN dispatch_record_id TEXT");
  }

  const awarenessColumns = listColumns(database, "awareness_snapshots");
  if (!awarenessColumns.has("signature")) {
    database.exec("ALTER TABLE awareness_snapshots ADD COLUMN signature TEXT NOT NULL DEFAULT ''");
  }

  const dispatchColumns = listColumns(database, "builder_dispatch_records");
  if (!dispatchColumns.has("completion_orchestration_id")) {
    database.exec("ALTER TABLE builder_dispatch_records ADD COLUMN completion_orchestration_id TEXT");
  }
  if (!dispatchColumns.has("verification_orchestration_id")) {
    database.exec("ALTER TABLE builder_dispatch_records ADD COLUMN verification_orchestration_id TEXT");
  }
}

export function getDatabase(): DatabaseSync {
  if (databaseInstance) {
    return databaseInstance;
  }

  ensureDirectories();
  const config = getConfig();
  const database = new DatabaseSync(config.dbPath);
  database.exec(SCHEMA_SQL);
  ensureSchemaMigrations(database);
  databaseInstance = database;
  return database;
}

export function closeDatabase(): void {
  if (databaseInstance) {
    databaseInstance.close();
    databaseInstance = null;
  }
}
