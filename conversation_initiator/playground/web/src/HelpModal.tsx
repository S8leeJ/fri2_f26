import { useEffect } from "react";

export default function HelpModal({ onClose }: { onClose: () => void }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="backdrop" onClick={onClose}>
      <div className="modal" role="dialog" aria-label="Help" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h2>How to use the playground</h2>
          <button className="ghost" onClick={onClose} aria-label="Close">×</button>
        </div>

        <h3>The idea</h3>
        <p>
          The robot gets one JSON snapshot of the scene. An LLM decides if it should speak, and a
          second call writes the line. Change the scene on the left, then talk to the robot or
          ask it to decide. Hover over any control to see what it does.
        </p>

        <h3>Quick start</h3>
        <ol>
          <li>Pick a preset, for example <code>022</code>, where someone asks a question.</li>
          <li>Type as the person and press <b>Send</b>. Or press <b>Check scene</b> to see if the
            robot would start a conversation on its own.</li>
          <li>Change one field, then send again. The robot's reply lists what you changed.</li>
          <li>When the robot does something odd, press <b>Save as vignette</b> to keep the case.</li>
        </ol>

        <h3>Reading a reply</h3>
        <ul>
          <li><b>Action</b>: greet, respond, wait, or remain_silent.</li>
          <li><b>Rule</b>: the rule the model says drove the choice.</li>
          <li><b>Red note</b>: a hard rule in code blocked the model. The line is not said.</li>
          <li><b>Bars</b>: the six rubric scores, 1 to 5. The model scores them before it picks.</li>
        </ul>

        <h3>Rules, highest first</h3>
        <table>
          <tbody>
            <tr><td>R1</td><td>Never greet someone in a conversation.</td></tr>
            <tr><td>R2</td><td>Never greet if the robot spoke under 30 s ago, or was ignored twice.</td></tr>
            <tr><td>R3</td><td>Do not greet someone walking past without facing the robot.</td></tr>
            <tr><td>R4</td><td>Do not greet someone at work unless they look at the robot.</td></tr>
            <tr><td>R5</td><td>Greet when they face the robot, are still or approaching, within about 3 m.</td></tr>
            <tr><td>R6</td><td>When evidence is thin, stay silent.</td></tr>
          </tbody>
        </table>

        <h3>Good to know</h3>
        <ul>
          <li>Groq's free tier allows about 4 turns a minute. A turn may wait about 15 s.</li>
          <li>The same scene can get different answers. Press Check scene twice to see it.</li>
          <li>The robot has no map. A reply with directions is made up.</li>
          <li>This tool does not produce study results. In the study, the participant decides what is right.</li>
        </ul>
      </div>
    </div>
  );
}
