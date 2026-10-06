import { useEffect, useRef, useState, type ReactNode } from "react";
import type { Ctx, Preset } from "./api";
import { DEFAULT_TARGET, enumOf, getPath, setPath } from "./scene";
import { TIPS } from "./tips";

interface Props {
  ctx: Ctx;
  schema: Ctx | null;
  presets: Preset[];
  presetId: string;
  onPreset: (id: string) => void;
  onChange: (c: Ctx) => void;
}

const PERSON_FIELDS = ["distance_m", "facing_robot", "gaze_at_robot_s", "motion", "activity", "in_conversation"];
const ROOM_PATHS = ["ambient.noise_level", "ambient.speech_now"];
const ROBOT_PATHS = ["robot.engaged", "robot.is_speaking", "robot.last_spoke_s_ago", "robot.consecutive_no_response"];
const GROUP_ORDER = ["respond", "greet", "wait", "remain_silent"];

const same = (a: unknown, b: unknown) => JSON.stringify(a ?? null) === JSON.stringify(b ?? null);
const presetName = (id: string) => id.replace(/^(\d+)_/, "$1 · ").replaceAll("_", " ");

export default function ScenePanel({ ctx, schema, presets, presetId, onPreset, onChange }: Props) {
  const savedTarget = useRef<Ctx | null>(null);
  const set = (path: string, value: unknown) => onChange(setPath(ctx, path, value));
  const preset = presets.find((p) => p.id === presetId);
  const base = preset?.context ?? {};
  const target = ctx.target;
  const baseTarget = base.target;
  const changed = (path: string) => !same(getPath(ctx, path), getPath(base, path));

  const togglePerson = (present: boolean) => {
    if (present) {
      set("target", savedTarget.current ?? baseTarget ?? DEFAULT_TARGET);
    } else {
      savedTarget.current = target;
      set("target", null);
    }
  };

  const resetPaths = (paths: string[]) =>
    onChange(paths.reduce((c, p) => setPath(c, p, getPath(base, p)), ctx));

  const personPaths = PERSON_FIELDS.map((f) => `target.${f}`);
  const personChanged = (target == null) !== (baseTarget == null) || personPaths.some(changed);
  const resetPerson = () => {
    if (!baseTarget || !target) return set("target", baseTarget ?? null);
    resetPaths(personPaths);
  };

  const bystanders: Ctx[] = ctx.bystanders ?? [];
  const setBystanders = (list: Ctx[]) => set("bystanders", list);
  const conversation: Ctx[] = ctx.conversation ?? [];

  const room = ctx.ambient ?? {};
  const robot = ctx.robot ?? {};

  return (
    <aside className="panel scene">
      <PresetCard presets={presets} preset={preset} onPreset={onPreset} />

      <Card id="room" title="Room" tip={TIPS.room}
        summary={join(room.noise_level ?? "noise ?", room.speech_now && "someone talking")}
        edited={ROOM_PATHS.some(changed)} onReset={() => resetPaths(ROOM_PATHS)}>
        <Segmented label="noise level" tip={TIPS.noise_level} value={room.noise_level}
          options={enumOf(schema, "ambient.noise_level")} changed={changed("ambient.noise_level")}
          onChange={(v) => set("ambient.noise_level", v)} />
        <div className="toggles">
          <Toggle label="someone talking now" tip={TIPS.speech_now} value={room.speech_now}
            changed={changed("ambient.speech_now")} onChange={(v) => set("ambient.speech_now", v)} />
        </div>
      </Card>

      <Card id="person" title="Person" tip={TIPS.person}
        summary={target ? join(`${Number(target.distance_m).toFixed(1)} m`,
          target.facing_robot ? "facing" : "not facing", target.motion, target.activity,
          target.in_conversation && "in conversation") : "nobody"}
        edited={personChanged} onReset={resetPerson}
        action={<Toggle label="present" tip={TIPS.person_present} value={target != null} onChange={togglePerson} />}>
        {target ? (
          <>
            <Field label="distance" tip={TIPS.distance_m} changed={changed("target.distance_m")}>
              <input type="range" min={0} max={8} step={0.1} value={target.distance_m}
                onChange={(e) => set("target.distance_m", Number(e.target.value))} />
              <span className="num">{Number(target.distance_m).toFixed(1)} m</span>
            </Field>
            <Segmented label="motion" tip={TIPS.motion} value={target.motion}
              options={enumOf(schema, "target.motion")} changed={changed("target.motion")}
              onChange={(v) => set("target.motion", v)} />
            <Segmented label="activity" tip={TIPS.activity} value={target.activity}
              options={enumOf(schema, "target.activity")} changed={changed("target.activity")}
              onChange={(v) => set("target.activity", v)} />
            <Num label="gaze" unit="s" tip={TIPS.gaze_at_robot_s} value={target.gaze_at_robot_s}
              changed={changed("target.gaze_at_robot_s")} onChange={(v) => set("target.gaze_at_robot_s", v)} />
            <div className="toggles">
              <Toggle label="facing robot" tip={TIPS.facing_robot} value={target.facing_robot}
                changed={changed("target.facing_robot")} onChange={(v) => set("target.facing_robot", v)} />
              <Toggle label="in a conversation" tip={TIPS.in_conversation} value={target.in_conversation}
                changed={changed("target.in_conversation")} onChange={(v) => set("target.in_conversation", v)} />
            </div>
          </>
        ) : (
          <p className="hint">Nobody is in front of the robot. Turn on "present" to add a person.</p>
        )}
      </Card>

      <Card id="bystanders" title="Bystanders" tip={TIPS.bystanders}
        summary={bystanders.length ? `${bystanders.length} in view` : "none"}
        edited={changed("bystanders")} onReset={() => resetPaths(["bystanders"])}>
        {bystanders.map((b, i) => {
          const update = (k: string, v: unknown) =>
            setBystanders(bystanders.map((x, j) => (j === i ? { ...x, [k]: v } : x)));
          return (
            <div key={i} className="bystander">
              <span className="who">#{i + 1}</span>
              <input type="number" min={0} step={0.1} value={b.distance_m} data-tip={TIPS.bystander_distance}
                onChange={(e) => update("distance_m", Number(e.target.value))} />
              <span className="unit">m</span>
              <Toggle label="facing" tip={TIPS.bystander_facing} value={b.facing_robot}
                onChange={(v) => update("facing_robot", v)} />
              <Toggle label="talking" tip={TIPS.bystander_talking} value={b.in_conversation}
                onChange={(v) => update("in_conversation", v)} />
              <button className="ghost small remove" data-tip={TIPS.remove_bystander}
                onClick={() => setBystanders(bystanders.filter((_, j) => j !== i))}>×</button>
            </div>
          );
        })}
        <button className="small dashed" data-tip={TIPS.add_bystander}
          onClick={() => setBystanders([...bystanders, { distance_m: 2.5, facing_robot: false, in_conversation: false }])}>
          + add bystander
        </button>
      </Card>

      <Card id="robot" title="Robot" tip={TIPS.robot_section}
        summary={join(robot.engaged ? "engaged" : "not engaged", robot.is_speaking && "speaking",
          typeof robot.last_spoke_s_ago === "number" ? `spoke ${robot.last_spoke_s_ago} s ago` : "never spoke",
          robot.consecutive_no_response ? `ignored ×${robot.consecutive_no_response}` : null)}
        edited={ROBOT_PATHS.some(changed)} onReset={() => resetPaths(ROBOT_PATHS)}>
        <div className="toggles">
          <Toggle label="engaged" tip={TIPS.engaged} value={robot.engaged}
            changed={changed("robot.engaged")} onChange={(v) => set("robot.engaged", v)} />
          <Toggle label="speaking now" tip={TIPS.is_speaking} value={robot.is_speaking}
            changed={changed("robot.is_speaking")} onChange={(v) => set("robot.is_speaking", v)} />
        </div>
        <Num label="last spoke" unit="s ago" tip={TIPS.last_spoke_s_ago} value={robot.last_spoke_s_ago}
          placeholder="never" emptyValue={null} changed={changed("robot.last_spoke_s_ago")}
          onChange={(v) => set("robot.last_spoke_s_ago", v)}
          extra={typeof robot.last_spoke_s_ago === "number" && (
            <button className="ghost small" data-tip={TIPS.never_spoke}
              onClick={() => set("robot.last_spoke_s_ago", null)}>never</button>
          )} />
        <Num label="times ignored" tip={TIPS.consecutive_no_response} value={robot.consecutive_no_response}
          integer changed={changed("robot.consecutive_no_response")}
          onChange={(v) => set("robot.consecutive_no_response", v)} />
      </Card>

      <Card id="conversation" title="Conversation" tip={TIPS.conversation} defaultOpen={false}
        summary={conversation.length ? `${conversation.length} turn${conversation.length === 1 ? "" : "s"}` : "empty"}
        action={conversation.length > 0 && (
          <button className="ghost small" data-tip={TIPS.clear_conversation}
            onClick={() => set("conversation", undefined)}>clear</button>
        )}>
        {conversation.length ? (
          <ol className="history">
            {conversation.map((turn, i) => (
              <li key={i} className={turn.speaker}>
                <span className="speaker">{turn.speaker}</span>
                <span className="text">{turn.text}</span>
                {typeof turn.s_ago === "number" && <span className="ago">{turn.s_ago} s</span>}
              </li>
            ))}
          </ol>
        ) : (
          <p className="hint">Nothing said yet. Each message and robot line is added here.</p>
        )}
      </Card>

      <RawJson ctx={ctx} onChange={onChange} />
    </aside>
  );
}

function join(...parts: unknown[]) {
  return parts.filter((p) => typeof p === "string" && p).join(" · ");
}

function PresetCard({ presets, preset, onPreset }: {
  presets: Preset[]; preset: Preset | undefined; onPreset: (id: string) => void;
}) {
  const [noteOpen, setNoteOpen] = useState(false);
  const groups = new Map<string, Preset[]>();
  for (const p of presets) {
    const key = p.expect ?? "not labelled";
    groups.set(key, [...(groups.get(key) ?? []), p]);
  }
  const keys = [...groups.keys()].sort((a, b) => rank(a) - rank(b));

  return (
    <section className="preset-card">
      <div className="preset-head">
        <span className="eyebrow">Scene</span>
        {preset && (
          <span className={`badge ${preset.expect ?? "none"}`} data-tip={TIPS.expected}>
            expect {preset.expect ?? "?"}
          </span>
        )}
      </div>
      <select className="preset" value={preset?.id ?? ""} data-tip={TIPS.preset}
        onChange={(e) => { setNoteOpen(false); onPreset(e.target.value); }}>
        {keys.map((k) => (
          <optgroup key={k} label={`Expect ${k}`}>
            {groups.get(k)!.map((p) => <option key={p.id} value={p.id}>{presetName(p.id)}</option>)}
          </optgroup>
        ))}
      </select>
      {preset?.note && (
        <p className={`hint note-text ${noteOpen ? "open" : ""}`} onClick={() => setNoteOpen(!noteOpen)}
          data-tip={noteOpen ? undefined : TIPS.preset_note}>
          {preset.note}
        </p>
      )}
    </section>
  );
}

function rank(expect: string) {
  const i = GROUP_ORDER.indexOf(expect);
  return i === -1 ? GROUP_ORDER.length : i;
}

function Card({ id, title, tip, summary, edited, onReset, action, defaultOpen = true, children }: {
  id: string;
  title: string;
  tip?: string;
  summary: string;
  edited?: boolean;
  onReset?: () => void;
  action?: ReactNode;
  defaultOpen?: boolean;
  children: ReactNode;
}) {
  const key = `playground.card.${id}`;
  const [open, setOpen] = useState(() => {
    const saved = localStorage.getItem(key);
    return saved == null ? defaultOpen : saved === "1";
  });
  const toggle = () => {
    localStorage.setItem(key, open ? "0" : "1");
    setOpen(!open);
  };

  return (
    <section className={`card ${open ? "open" : ""}`}>
      <div className="card-head">
        <button className="card-title" onClick={toggle} data-tip={tip}>
          <span className="chev">{open ? "▾" : "▸"}</span>
          <span className="title">{title}</span>
          {edited && <span className="edited-dot" />}
          <span className="summary">{summary}</span>
        </button>
        {edited && onReset && (
          <button className="ghost small" data-tip={TIPS.reset_section} onClick={onReset}>reset</button>
        )}
        {action}
      </div>
      {open && <div className="card-body">{children}</div>}
    </section>
  );
}

function Field({ label, tip, changed, children }: {
  label: string; tip: string; changed?: boolean; children: ReactNode;
}) {
  return (
    <div className="field" data-tip={tip}>
      <span className={`label ${changed ? "changed" : ""}`}>{label}</span>
      {children}
    </div>
  );
}

function Toggle({ label, tip, value, changed, onChange }: {
  label: string; tip: string; value: unknown; changed?: boolean; onChange: (v: boolean) => void;
}) {
  return (
    <label className={`toggle ${changed ? "changed" : ""}`} data-tip={tip}>
      <input type="checkbox" checked={value === true} onChange={(e) => onChange(e.target.checked)} />
      <span className="switch" />
      <span>{label}</span>
    </label>
  );
}

function Segmented({ label, tip, value, options, changed, onChange }: {
  label: string; tip: string; value: unknown; options: string[]; changed?: boolean;
  onChange: (v: string | undefined) => void;
}) {
  return (
    <Field label={label} tip={tip} changed={changed}>
      <div className="segmented">
        {options.map((o) => (
          <button key={o} className={value === o ? "on" : ""} onClick={() => onChange(o)}>{o}</button>
        ))}
        <button className={`unset ${value == null ? "on" : ""}`} data-tip={TIPS.not_measured}
          onClick={() => onChange(undefined)}>?</button>
      </div>
    </Field>
  );
}

function Num({ label, unit, tip, value, onChange, changed, extra, placeholder = "not measured", emptyValue, integer }: {
  label: string;
  unit?: string;
  tip: string;
  value: unknown;
  onChange: (v: number | null | undefined) => void;
  changed?: boolean;
  extra?: ReactNode;
  placeholder?: string;
  emptyValue?: null;
  integer?: boolean;
}) {
  const n = typeof value === "number" ? value : null;
  const step = integer ? 1 : 0.5;
  const bump = (d: number) => onChange(Math.max(0, (n ?? 0) + d));
  return (
    <Field label={label} tip={tip} changed={changed}>
      <div className="stepper">
        <button className="small" onClick={() => bump(-step)} disabled={n == null || n <= 0}>−</button>
        <input type="number" min={0} step={step} placeholder={placeholder} value={n ?? ""}
          onChange={(e) => {
            const raw = e.target.value;
            if (raw === "") return onChange(emptyValue);
            onChange(integer ? Math.round(Number(raw)) : Number(raw));
          }} />
        <button className="small" onClick={() => bump(step)}>+</button>
      </div>
      {unit && <span className="unit">{unit}</span>}
      {extra}
    </Field>
  );
}

function RawJson({ ctx, onChange }: { ctx: Ctx; onChange: (c: Ctx) => void }) {
  const [text, setText] = useState(() => JSON.stringify(ctx, null, 2));
  const [error, setError] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    if (!dirty) setText(JSON.stringify(ctx, null, 2));
  }, [ctx, dirty]);

  const apply = () => {
    try {
      onChange(JSON.parse(text));
      setError(null);
      setDirty(false);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  return (
    <Card id="raw" title="Raw JSON" tip={TIPS.raw_json} summary="what gets sent" defaultOpen={false}>
      <textarea spellCheck={false} value={text}
        onChange={(e) => { setText(e.target.value); setDirty(true); }} />
      {dirty && (
        <div className="row">
          <button className="small primary" onClick={apply}>apply</button>
          <button className="small" onClick={() => { setDirty(false); setError(null); }}>discard</button>
        </div>
      )}
      {error && <p className="error">{error}</p>}
    </Card>
  );
}
