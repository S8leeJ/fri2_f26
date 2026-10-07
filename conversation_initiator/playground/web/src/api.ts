export type Ctx = Record<string, any>;

export interface Provider {
  name: string;
  model: string;
}

export interface Preset {
  id: string;
  expect: string | null;
  note: string;
  context: Ctx;
}

export interface Rubric {
  invitation: number;
  interruption_cost: number;
  urgency: number;
  redundancy: number;
  ambient_fit: number;
  addressivity: number;
}

export interface Decision {
  rubric: Rubric;
  action: string;
  category: string;
  rule_fired: string;
  confidence: number;
  recheck_in_ms: number;
}

export interface Speech {
  text: string;
  volume: string;
  rate: string;
  pitch: string;
}

export interface TurnResult {
  action_raw: string | null;
  action_final: string;
  blocked_by: string | null;
  decision: Decision | null;
  speech: Speech | null;
  speech_error: string | null;
  ms1: number | null;
  ms2: number | null;
  model: string | null;
}

async function call<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(path, body === undefined ? undefined : {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail);
    throw new Error(`${res.status}: ${detail ?? res.statusText}`);
  }
  return data as T;
}

async function speak(speech: Speech): Promise<{ url: string; timing: string }> {
  const res = await fetch("/api/speak", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(speech),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(`${res.status}: ${data.detail ?? res.statusText}`);
  }
  return { url: URL.createObjectURL(await res.blob()), timing: res.headers.get("X-TTS") ?? "" };
}

async function listen(audio: Blob): Promise<{ text: string; ms: number }> {
  const res = await fetch("/api/listen", {
    method: "POST",
    headers: { "Content-Type": audio.type || "application/octet-stream" },
    body: audio,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(`${res.status}: ${data.detail ?? res.statusText}`);
  return data;
}

export async function play(speech: Speech): Promise<string> {
  const { url, timing } = await speak(speech);
  const audio = new Audio(url);
  audio.onended = () => URL.revokeObjectURL(url);
  await audio.play();
  return timing;
}

export const api = {
  providers: () => call<Provider[]>("/api/providers"),
  presets: () => call<Preset[]>("/api/presets"),
  schema: () => call<Ctx>("/api/schema"),
  turn: (provider: string, model: string | null, context: Ctx) =>
    call<TurnResult>("/api/turn", { provider, model, context }),
  voice: () => call<{ tts: string | null; stt: string | null }>("/api/voice"),
  listen,
  saveVignette: (context: Ctx, note: string) =>
    call<{ file: string }>("/api/vignettes", { context, note }),
};
