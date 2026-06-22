import { execFileSync } from "node:child_process";
import fs from "node:fs";

export type DumpRow = {
  rowid: number;
  text: string | null;
  attributedBody: Buffer | null;
  date: number;
  chatIdentifier: string;
  associatedMessageType: number;
};

const DUMP_FIELD_SEP = "|";

// Framework noise that shows up as printable runs inside an attributedBody
// NSKeyedArchiver blob — not part of the actual message text.
const ATTRIBUTED_BODY_NOISE = new Set([
  "streamtyped",
  "NSAttributedString",
  "NSObject",
  "NSString",
  "NSMutableString",
  "NSMutableAttributedString",
  "NSDictionary",
  "NSMutableDictionary",
  "NSArray",
  "NSNumber",
  "NSValue",
  "__kIMMessagePartAttributeName",
  "__kIMDataDetectedAttributeName",
  "__kIMLinkAttributeName"
]);

const PRINTABLE_RUN_RE = /[\x20-\x7e]{4,}/g;
const LEADING_JUNK_RE = /^[^A-Za-z0-9]+/;
const OBJECT_REPLACEMENT_CHAR = "￼";

export function readDumpRows(dumpPath: string): DumpRow[] {
  if (!fs.existsSync(dumpPath)) {
    return [];
  }

  const rows = fs
    .readFileSync(dumpPath, "utf8")
    .split("\n")
    .filter((line) => line.trim().length > 0)
    .map((line) => line.split(DUMP_FIELD_SEP))
    .map(([rowid, textHex, bodyHex, date, chatIdentifier, assocType]) => ({
      rowid: Number(rowid),
      text: textHex ? Buffer.from(textHex, "hex").toString("utf8") : null,
      attributedBody: bodyHex ? Buffer.from(bodyHex, "hex") : null,
      date: date ? Number(date) : 0,
      chatIdentifier: chatIdentifier ?? "",
      associatedMessageType: assocType ? Number(assocType) : 0
    }));

  return rows.sort((a, b) => a.rowid - b.rowid);
}

function extractFromAttributedBody(blob: Buffer): string | null {
  // attributedBody is an NSKeyedArchiver blob (used whenever a message isn't
  // plain unstyled text — links, mentions, many recent macOS versions even
  // for ordinary text). Rather than implement a full unarchiver, pull every
  // printable run out of the raw bytes, drop the known framework
  // class-name/key noise, and take the longest survivor — in practice
  // that's the actual message body.
  const decoded = blob.toString("latin1");
  const candidates = [...decoded.matchAll(PRINTABLE_RUN_RE)]
    .map((match) => match[0])
    .filter((run) => !ATTRIBUTED_BODY_NOISE.has(run));

  if (!candidates.length) {
    return null;
  }

  const best = candidates.reduce((longest, candidate) => (candidate.length > longest.length ? candidate : longest));
  const cleaned = best.replace(LEADING_JUNK_RE, "").trim();
  return cleaned || null;
}

export function extractText(text: string | null, attributedBody: Buffer | null): string | null {
  const candidate = text || (attributedBody ? extractFromAttributedBody(attributedBody) : null);
  if (!candidate) {
    return null;
  }

  const cleaned = candidate.split(OBJECT_REPLACEMENT_CHAR).join("").trim();
  return cleaned || null;
}

export function isDumpStale(dumpPath: string, maxAgeMs: number): boolean {
  if (!fs.existsSync(dumpPath)) {
    return true;
  }

  const ageMs = Date.now() - fs.statSync(dumpPath).mtime.getTime();
  return ageMs > maxAgeMs;
}

function escapeAppleScriptString(value: string): string {
  return value.replace(/\\/g, "\\\\").replace(/"/g, '\\"');
}

export function sendImessage(to: string, body: string): boolean {
  const script = [
    'tell application "Messages"',
    "    set theService to 1st service whose service type = iMessage",
    `    set theBuddy to buddy "${escapeAppleScriptString(to)}" of theService`,
    `    send "${escapeAppleScriptString(body)}" to theBuddy`,
    "end tell"
  ].join("\n");

  try {
    execFileSync("osascript", ["-e", script], { encoding: "utf8" });
    return true;
  } catch {
    return false;
  }
}
