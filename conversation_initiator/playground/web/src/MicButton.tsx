import { useEffect, useRef, useState } from "react";
import { TIPS } from "./tips";

interface Props {
  disabled: boolean;
  onAudio: (audio: Blob) => void;
  onError: (message: string) => void;
}

export default function MicButton({ disabled, onAudio, onError }: Props) {
  const [recording, setRecording] = useState(false);
  const recorder = useRef<MediaRecorder | null>(null);

  useEffect(() => () => recorder.current?.stop(), []);

  const start = async () => {
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (e) {
      onError((e as Error).message);
      return;
    }
    const r = new MediaRecorder(stream);
    const chunks: Blob[] = [];
    r.ondataavailable = (e) => { if (e.data.size) chunks.push(e.data); };
    r.onstop = () => {
      stream.getTracks().forEach((t) => t.stop());
      recorder.current = null;
      setRecording(false);
      onAudio(new Blob(chunks, { type: r.mimeType }));
    };
    r.start();
    recorder.current = r;
    setRecording(true);
  };

  return (
    <button className={recording ? "recording" : ""} data-tip={TIPS.mic}
      disabled={disabled && !recording}
      onClick={() => (recording ? recorder.current?.stop() : start())}>
      {recording ? "■ Stop" : "🎤 Talk"}
    </button>
  );
}
