import type { Ctx, TurnResult } from "./api";

const SPEAKS = ["greet", "respond"];
const MAX_RECENT = 5;
// Schema maxItems for conversation[].
const MAX_CONVERSATION = 20;

function addTurn(c: Ctx, speaker: "person" | "robot", text: string) {
  c.conversation = [...(c.conversation ?? []), { speaker, text, s_ago: 0 }].slice(-MAX_CONVERSATION);
}

export const clone = (c: Ctx): Ctx => structuredClone(c);

export const DEFAULT_TARGET: Ctx = {
  distance_m: 1.5,
  facing_robot: true,
  motion: "stationary",
  activity: "idle",
  in_conversation: false,
};

/** Set a dotted path. undefined deletes the key, so "not measured" is omitted, not faked. */
export function setPath(c: Ctx, path: string, value: unknown): Ctx {
  const out = clone(c);
  const keys = path.split(".");
  let node = out;
  for (const k of keys.slice(0, -1)) {
    if (node[k] == null || typeof node[k] !== "object") node[k] = {};
    node = node[k];
  }
  const last = keys[keys.length - 1];
  if (value === undefined) delete node[last];
  else node[last] = value;
  return out;
}

export function getPath(c: Ctx, path: string): any {
  return path.split(".").reduce((n, k) => (n == null ? undefined : n[k]), c);
}

function flatten(v: any, prefix: string, out: Record<string, string>) {
  if (v !== null && typeof v === "object" && !Array.isArray(v)) {
    for (const k of Object.keys(v)) flatten(v[k], prefix ? `${prefix}.${k}` : k, out);
    if (Object.keys(v).length === 0 && prefix) out[prefix] = "{}";
  } else {
    out[prefix] = JSON.stringify(v);
  }
}

// Bumped by every turn or time step, so listing them would bury the real changes.
const DIFF_IGNORE = ["t", "recent_decisions", "since_last_decision_s", "conversation"];

export function diff(before: Ctx | null, after: Ctx): string[] {
  if (!before) return [];
  const a: Record<string, string> = {};
  const b: Record<string, string> = {};
  flatten(before, "", a);
  flatten(after, "", b);
  const keys = [...new Set([...Object.keys(a), ...Object.keys(b)])].sort();
  return keys
    .filter((k) => !DIFF_IGNORE.some((p) => k === p || k.startsWith(p + ".")))
    .filter((k) => a[k] !== b[k])
    .map((k) => `${k}: ${a[k] ?? "(unset)"} -> ${b[k] ?? "(unset)"}`);
}

/** The scene sent for one turn. text is what the person said, or null for "Check scene". */
export function prepareTurn(c: Ctx, text: string | null, unfinished: boolean): Ctx {
  const out = clone(c);
  if (!out.target) return out;
  if (text) {
    out.target.speech = {
      detected: true,
      partial_transcript: text,
      syntactically_complete: !unfinished,
    };
    // The audio node only transcribes while engaged, so a transcript implies it.
    out.robot = { ...(out.robot ?? {}), engaged: true, consecutive_no_response: 0 };
    addTurn(out, "person", text);
  } else {
    delete out.target.speech;
  }
  return out;
}

/** What the initiator writes back after a decision, so the next turn sees it. */
export function applyResult(sent: Ctx, r: TurnResult): Ctx {
  const out = clone(sent);
  const reason = r.blocked_by ?? r.decision?.rule_fired ?? null;
  out.recent_decisions = [
    { s_ago: 0, action: r.action_final, reason },
    ...(out.recent_decisions ?? []),
  ].slice(0, MAX_RECENT);
  out.since_last_decision_s = 0;
  if (SPEAKS.includes(r.action_final) && r.speech) {
    out.robot = {
      ...(out.robot ?? {}),
      last_utterance: r.speech.text,
      last_spoke_s_ago: 0,
      engaged: true,
    };
    addTurn(out, "robot", r.speech.text);
  }
  return out;
}

export function advance(c: Ctx, seconds: number): Ctx {
  const out = clone(c);
  if (typeof out.t === "number") out.t += seconds;
  if (typeof out.since_last_decision_s === "number") out.since_last_decision_s += seconds;
  if (out.robot && typeof out.robot.last_spoke_s_ago === "number") {
    out.robot.last_spoke_s_ago += seconds;
  }
  for (const d of out.recent_decisions ?? []) d.s_ago += seconds;
  for (const turn of out.conversation ?? []) {
    if (typeof turn.s_ago === "number") turn.s_ago += seconds;
  }
  return out;
}

export function ignored(c: Ctx): Ctx {
  const n = getPath(c, "robot.consecutive_no_response") ?? 0;
  return setPath(c, "robot.consecutive_no_response", n + 1);
}

export function enumOf(schema: Ctx | null, path: string): string[] {
  let node: any = schema;
  for (const k of path.split(".")) node = node?.properties?.[k];
  return (node?.enum ?? []).filter((v: unknown) => v !== null);
}
