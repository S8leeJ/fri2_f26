import { useEffect, useState } from "react";
import { api, type Ctx, type Preset, type Provider } from "./api";
import ChatPanel, { type Message } from "./ChatPanel";
import HelpModal from "./HelpModal";
import ScenePanel from "./ScenePanel";
import Splitter, { useSceneWidth } from "./Splitter";
import { advance, applyResult, clone, diff, ignored, prepareTurn } from "./scene";
import { TIPS } from "./tips";
import TooltipLayer from "./Tooltip";

const START_PRESET = "022";

export default function App() {
  const [providers, setProviders] = useState<Provider[]>([]);
  const [provider, setProvider] = useState("");
  const [model, setModel] = useState("");
  const [presets, setPresets] = useState<Preset[]>([]);
  const [schema, setSchema] = useState<Ctx | null>(null);
  const [presetId, setPresetId] = useState("");
  const [ctx, setCtx] = useState<Ctx | null>(null);
  // The scene as of the last turn, so each robot bubble can say what you changed.
  const [lastCtx, setLastCtx] = useState<Ctx | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [busy, setBusy] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [helpOpen, setHelpOpen] = useState(false);
  const [sceneWidth, setSceneWidth] = useSceneWidth();

  const push = (...m: Message[]) => setMessages((prev) => [...prev, ...m]);

  useEffect(() => {
    Promise.all([api.providers(), api.presets(), api.schema()])
      .then(([prov, pre, sch]) => {
        setProviders(prov);
        setProvider(prov[0]?.name ?? "");
        setPresets(pre);
        setSchema(sch);
        const first = pre.find((p) => p.id.startsWith(START_PRESET)) ?? pre[0];
        if (first) loadPreset(first);
      })
      .catch((e) => setLoadError(`Cannot reach the server: ${e.message}. Is uvicorn running on port 8000?`));
  }, []);

  const loadPreset = (p: Preset) => {
    setPresetId(p.id);
    setCtx(clone(p.context));
    setLastCtx(clone(p.context));
    setMessages([{ kind: "note", text: `Loaded ${p.id}.` }]);
  };

  const runTurn = async (text: string | null, unfinished = false) => {
    if (!ctx || !provider) return;
    const changes = diff(lastCtx, ctx);
    const sent = prepareTurn(ctx, text, unfinished);
    push(text ? { kind: "person", text, unfinished } : { kind: "check" });
    setBusy(true);
    try {
      const result = await api.turn(provider, model.trim() || null, sent);
      push({ kind: "robot", result, provider, changes });
      const next = applyResult(sent, result);
      setCtx(next);
      setLastCtx(next);
    } catch (e) {
      push({ kind: "error", text: (e as Error).message });
    } finally {
      setBusy(false);
    }
  };

  const saveVignette = async () => {
    if (!ctx) return;
    const note = window.prompt("Short note for this vignette (what makes it interesting?)", "");
    if (note === null) return;
    try {
      const { file } = await api.saveVignette(ctx, note);
      push({ kind: "note", text: `Saved as vignettes/${file} (unlabelled).` });
      setPresets(await api.presets());
    } catch (e) {
      push({ kind: "error", text: (e as Error).message });
    }
  };

  if (loadError) return <div className="fatal">{loadError}</div>;
  if (!ctx) return <div className="fatal">Loading...</div>;

  const current = providers.find((p) => p.name === provider);

  return (
    <div className="app">
      <header>
        <div className="brand">
          <h1>Read the Room</h1>
          <span className="subtitle">playground · when should the robot speak?</span>
        </div>
        <span className="spacer" />
        <label className="head-field" data-tip={TIPS.provider}>
          <span>provider</span>
          <select value={provider} onChange={(e) => { setProvider(e.target.value); setModel(""); }}>
            {providers.map((p) => <option key={p.name} value={p.name}>{p.name}</option>)}
          </select>
        </label>
        <label className="head-field" data-tip={TIPS.model}>
          <span>model</span>
          <input value={model} placeholder={current?.model ?? ""} onChange={(e) => setModel(e.target.value)} />
        </label>
        <button data-tip={TIPS.save} onClick={saveVignette}>Save as vignette</button>
        <button className="help-btn" data-tip={TIPS.help} onClick={() => setHelpOpen(true)}>? Help</button>
      </header>
      <TooltipLayer />
      {helpOpen && <HelpModal onClose={() => setHelpOpen(false)} />}
      {providers.length === 0 && (
        <div className="note error">No provider keys found in mvp/.env. Add one and restart the server.</div>
      )}
      <main style={{ gridTemplateColumns: `${sceneWidth}px 0 1fr` }}>
        <ScenePanel ctx={ctx} schema={schema} presets={presets} presetId={presetId}
          onPreset={(id) => { const p = presets.find((x) => x.id === id); if (p) loadPreset(p); }}
          onChange={setCtx} />
        <Splitter onResize={setSceneWidth} />
        <ChatPanel messages={messages} busy={busy} canSpeak={ctx.target != null}
          onSend={(t, u) => runTurn(t, u)}
          onCheck={() => runTurn(null)}
          onAdvance={(s) => { setCtx(advance(ctx, s)); push({ kind: "note", text: `${s} s pass.` }); }}
          onIgnored={() => { setCtx(ignored(ctx)); push({ kind: "note", text: "The person ignored the robot." }); }}
          onReset={() => { const p = presets.find((x) => x.id === presetId); if (p) loadPreset(p); }} />
      </main>
    </div>
  );
}
