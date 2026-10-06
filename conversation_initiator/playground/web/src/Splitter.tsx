import { useEffect, useState } from "react";

const KEY = "playground.sceneWidth";
export const DEFAULT_WIDTH = 360;
const MIN = 260;
const MAX_SHARE = 0.65;

const clamp = (w: number) => Math.round(Math.min(Math.max(w, MIN), window.innerWidth * MAX_SHARE));

/** Width of the scene panel, kept across reloads. */
export function useSceneWidth() {
  const [width, setWidth] = useState(() => {
    const saved = Number(localStorage.getItem(KEY));
    return saved ? clamp(saved) : DEFAULT_WIDTH;
  });
  useEffect(() => localStorage.setItem(KEY, String(width)), [width]);
  return [width, (w: number) => setWidth(clamp(w))] as const;
}

export default function Splitter({ onResize }: { onResize: (width: number) => void }) {
  const [dragging, setDragging] = useState(false);

  useEffect(() => {
    if (!dragging) return;
    const move = (e: MouseEvent) => onResize(e.clientX);
    const stop = () => setDragging(false);
    document.body.classList.add("resizing");
    document.addEventListener("mousemove", move);
    document.addEventListener("mouseup", stop);
    return () => {
      document.body.classList.remove("resizing");
      document.removeEventListener("mousemove", move);
      document.removeEventListener("mouseup", stop);
    };
  }, [dragging, onResize]);

  return (
    <div className={`splitter ${dragging ? "active" : ""}`} role="separator" aria-orientation="vertical"
      data-tip="Drag to resize the scene panel. Double-click to reset."
      onMouseDown={(e) => { e.preventDefault(); setDragging(true); }}
      onDoubleClick={() => onResize(DEFAULT_WIDTH)} />
  );
}
