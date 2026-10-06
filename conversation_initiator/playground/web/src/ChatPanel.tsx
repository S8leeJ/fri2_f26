import { useEffect, useRef, useState } from "react";
import type { Rubric, TurnResult } from "./api";
import { TIPS } from "./tips";

export type Message =
  | { kind: "person"; text: string; unfinished: boolean }
  | { kind: "check" }
  | { kind: "robot"; result: TurnResult; provider: string; changes: string[] }
  | { kind: "note"; text: string }
  | { kind: "error"; text: string };

interface Props {
  messages: Message[];
  busy: boolean;
  canSpeak: boolean;
  onSend: (text: string, unfinished: boolean) => void;
  onCheck: () => void;
  onAdvance: (s: number) => void;
  onIgnored: () => void;
  onReset: () => void;
}

const SAMPLES = [
  "Where is the elevator?",
  "How are you doing?",
  "Can you carry this for me?",
  "Oh cool, a robot.",
];

export default function ChatPanel(p: Props) {
  const [text, setText] = useState("");
  const [unfinished, setUnfinished] = useState(false);
  const end = useRef<HTMLDivElement>(null);

  useEffect(() => {
    end.current?.scrollIntoView({ behavior: "smooth" });
  }, [p.messages, p.busy]);

  const send = (t = text.trim()) => {
    if (!t || p.busy || !p.canSpeak) return;
    p.onSend(t, unfinished);
    setText("");
    setUnfinished(false);
  };

  const hasTurns = p.messages.some((m) => m.kind === "robot" || m.kind === "error");

  return (
    <section className="panel chat">
      <div className="log">
        {p.messages.map((m, i) => <Bubble key={i} m={m} />)}
        {!hasTurns && !p.busy && (
          <div className="empty">
            <p><b>Talk to the robot</b>, or press <b>Check scene</b> to see if it would start a conversation.</p>
            {p.canSpeak && (
              <div className="samples">
                {SAMPLES.map((s) => (
                  <button key={s} className="chip" onClick={() => send(s)}>{s}</button>
                ))}
              </div>
            )}
          </div>
        )}
        {p.busy && <div className="bubble robot pending"><span className="dots"><i /><i /><i /></span></div>}
        <div ref={end} />
      </div>

      <div className="composer">
        <input value={text} data-tip={TIPS.input}
          placeholder={p.canSpeak ? "Say something to the robot..." : "No person present. Use Check scene."}
          disabled={!p.canSpeak || p.busy} onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send()} />
        <button className="primary" data-tip={TIPS.send}
          disabled={!p.canSpeak || p.busy || !text.trim()} onClick={() => send()}>Send</button>
        <button data-tip={TIPS.check} disabled={p.busy} onClick={p.onCheck}>Check scene</button>
      </div>

      <div className="tools">
        <label className="toggle" data-tip={TIPS.unfinished}>
          <input type="checkbox" checked={unfinished} onChange={(e) => setUnfinished(e.target.checked)} />
          <span className="switch" />
          <span>unfinished sentence</span>
        </label>
        <span className="spacer" />
        <div className="group">
          <span className="group-label">Time</span>
          <button className="small" data-tip={TIPS.plus5} disabled={p.busy} onClick={() => p.onAdvance(5)}>+5 s</button>
          <button className="small" data-tip={TIPS.plus30} disabled={p.busy} onClick={() => p.onAdvance(30)}>+30 s</button>
        </div>
        <div className="group">
          <span className="group-label">Person</span>
          <button className="small" data-tip={TIPS.ignored} disabled={p.busy} onClick={p.onIgnored}>Ignored</button>
        </div>
        <button className="small" data-tip={TIPS.reset} disabled={p.busy} onClick={p.onReset}>↺ Reset</button>
      </div>
    </section>
  );
}

function Bubble({ m }: { m: Message }) {
  switch (m.kind) {
    case "person":
      return (
        <div className="bubble person">
          {m.text}
          {m.unfinished && <span className="tag">unfinished</span>}
        </div>
      );
    case "check":
      return <div className="bubble person muted">(checks the scene, says nothing)</div>;
    case "note":
      return <div className="note">{m.text}</div>;
    case "error":
      return <div className="note error">⚠ {m.text}</div>;
    case "robot":
      return <RobotBubble result={m.result} provider={m.provider} changes={m.changes} />;
  }
}

const NO_LINE: Record<string, string> = {
  remain_silent: "(stays silent)",
  wait: "(waits)",
};

function RobotBubble({ result: r, provider, changes }: { result: TurnResult; provider: string; changes: string[] }) {
  const d = r.decision;
  let line = NO_LINE[r.action_final];
  let failed = false;
  if (!line) {
    if (r.speech) line = `"${r.speech.text}"`;
    else {
      failed = true;
      line = provider === "jev"
        ? "(jev decides only; it cannot write the line)"
        : `(no line: ${r.speech_error ?? "speech call returned nothing"})`;
    }
  }

  return (
    <div className={`bubble robot act-${r.action_final}`}>
      {changes.length > 0 && (
        <div className="changes" data-tip={TIPS.changes}>
          <span className="changes-label">changed</span>
          {changes.map((c) => <code key={c}>{c}</code>)}
        </div>
      )}
      <div className={`line ${failed ? "failed" : ""}`}>{line}</div>
      <div className="meta">
        <span className={`badge ${r.action_final}`} data-tip={TIPS.action[r.action_final]}>{r.action_final}</span>
        {r.speech && (
          <span className="pill" data-tip={TIPS.voice}>{r.speech.volume} · {r.speech.rate} · {r.speech.pitch}</span>
        )}
        {r.blocked_by && (
          <span className="blocked" data-tip={TIPS.blocked}>
            ⛔ post-filter blocked {r.action_raw ?? "speech"}: {r.blocked_by}
          </span>
        )}
      </div>
      {d && (
        <>
          <div className="meta">
            <span data-tip={TIPS.rule}><b>{d.rule_fired}</b></span>
            <span data-tip={TIPS.category}>{d.category.replace(/_/g, " ")}</span>
            <span data-tip={TIPS.confidence}>conf {d.confidence.toFixed(2)}</span>
            <span data-tip={TIPS.recheck}>recheck {d.recheck_in_ms} ms</span>
          </div>
          <RubricBars rubric={d.rubric} />
        </>
      )}
      <div className="meta faint" data-tip={r.ms1 == null ? undefined : TIPS.latency}>
        {r.ms1 == null
          ? "no model call (nobody present)"
          : `${provider} · ${r.model} · decision ${Math.round(r.ms1)} ms` +
            (r.ms2 != null ? ` · line ${Math.round(r.ms2)} ms` : "")}
      </div>
    </div>
  );
}

const RUBRIC_LABELS: [keyof Rubric, string][] = [
  ["invitation", "invite"],
  ["interruption_cost", "cost"],
  ["urgency", "urgency"],
  ["redundancy", "redund."],
  ["ambient_fit", "fit"],
  ["addressivity", "address"],
];

function RubricBars({ rubric }: { rubric: Rubric }) {
  return (
    <div className="rubric">
      {RUBRIC_LABELS.map(([k, label]) => (
        <div key={k} className="bar" data-tip={TIPS.rubric[k]}>
          <span className="bar-label">{label}</span>
          <div className="track"><div className="fill" style={{ width: `${rubric[k] * 20}%` }} /></div>
          <span className="num">{rubric[k]}</span>
        </div>
      ))}
    </div>
  );
}
