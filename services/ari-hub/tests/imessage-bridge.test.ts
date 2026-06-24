import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import { extractText, isDumpStale, readDumpRows, sendImessage } from "../src/core/ari-spine/imessage-bridge";

function tempDumpPath(): string {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "imessage-bridge-test-"));
  return path.join(dir, "imessage-dump.tsv");
}

function hex(value: string): string {
  return Buffer.from(value, "latin1").toString("hex");
}

test("readDumpRows parses TSV fields, hex-decodes text and attributedBody, and sorts by rowid", () => {
  const dumpFile = tempDumpPath();
  const lines = [
    `2|${hex("second")}||200|+10000000000|0`,
    `1|${hex("first")}||100|self@example.com|0`
  ];
  fs.writeFileSync(dumpFile, lines.join("\n") + "\n", "utf8");

  const rows = readDumpRows(dumpFile);
  assert.equal(rows.length, 2);
  assert.equal(rows[0].rowid, 1);
  assert.equal(rows[0].text, "first");
  assert.equal(rows[0].chatIdentifier, "self@example.com");
  assert.equal(rows[1].rowid, 2);
  assert.equal(rows[1].text, "second");
});

test("readDumpRows returns an empty array when the dump file does not exist", () => {
  const missing = path.join(os.tmpdir(), `nonexistent-${Date.now()}.tsv`);
  assert.deepEqual(readDumpRows(missing), []);
});

test("readDumpRows decodes attributedBody as a hex-encoded buffer when present", () => {
  const dumpFile = tempDumpPath();
  const bodyHex = hex("streamtyped\x00\x00the real message\x00\x00");
  fs.writeFileSync(dumpFile, `1||${bodyHex}|100|+10000000000|0\n`, "utf8");

  const [row] = readDumpRows(dumpFile);
  assert.equal(row.text, null);
  assert.ok(row.attributedBody);
  assert.equal(row.attributedBody?.toString("latin1").includes("the real message"), true);
});

test("extractText prefers plain text over attributedBody", () => {
  assert.equal(extractText("hello there", Buffer.from("irrelevant")), "hello there");
});

test("extractText falls back to attributedBody, filtering known NSKeyedArchiver noise", () => {
  const blob = Buffer.from(
    "\x04\x86streamtyped\x00\x84\x01NSMutableString\x00\x01+\x00Hello, this is the real message text\x00\x86",
    "latin1"
  );
  assert.equal(extractText(null, blob), "Hello, this is the real message text");
});

test("extractText strips leading junk and the object-replacement character", () => {
  const blob = Buffer.from("\x00\x86NSObject\x00:::Actual body text here￼\x00", "latin1");
  assert.equal(extractText(null, blob), "Actual body text here");
});

test("extractText returns null when there is no text and no usable attributedBody", () => {
  assert.equal(extractText(null, null), null);
  assert.equal(extractText("", null), null);
  const noiseOnly = Buffer.from("\x00streamtyped\x00NSDictionary\x00", "latin1");
  assert.equal(extractText(null, noiseOnly), null);
});

test("isDumpStale is true when the file is missing or older than the threshold, false otherwise", () => {
  const dumpFile = tempDumpPath();
  fs.writeFileSync(dumpFile, "1|68656c6c6f||100|+10000000000|0\n", "utf8");

  assert.equal(isDumpStale(dumpFile, 5 * 60 * 1000), false);

  const old = new Date(Date.now() - 10 * 60 * 1000);
  fs.utimesSync(dumpFile, old, old);
  assert.equal(isDumpStale(dumpFile, 5 * 60 * 1000), true);

  assert.equal(isDumpStale(path.join(os.tmpdir(), `missing-${Date.now()}.tsv`), 5 * 60 * 1000), true);
});

test("sendImessage returns false instead of throwing when osascript is unavailable or fails", () => {
  const originalPath = process.env.PATH;
  process.env.PATH = "";
  try {
    assert.equal(sendImessage("+10000000000", "test"), false);
  } finally {
    process.env.PATH = originalPath;
  }
});
