import { useEffect, useState } from "react";

interface Shown {
  text: string;
  x: number;
  y: number;
  below: boolean;
}

const GAP = 8;
const WIDTH = 280;

/** One tooltip for the page. Any element with a data-tip attribute gets it on hover. */
export default function TooltipLayer() {
  const [tip, setTip] = useState<Shown | null>(null);

  useEffect(() => {
    let timer: number | undefined;

    const show = (e: Event) => {
      const el = (e.target as HTMLElement | null)?.closest<HTMLElement>("[data-tip]");
      window.clearTimeout(timer);
      if (!el) return setTip(null);
      timer = window.setTimeout(() => {
        const r = el.getBoundingClientRect();
        const below = r.top < 90;
        const x = Math.min(Math.max(r.left + r.width / 2, WIDTH / 2 + GAP), window.innerWidth - WIDTH / 2 - GAP);
        setTip({ text: el.dataset.tip!, x, y: below ? r.bottom + GAP : r.top - GAP, below });
      }, 250);
    };
    const hide = () => {
      window.clearTimeout(timer);
      setTip(null);
    };
    const leftWindow = (e: MouseEvent) => {
      if (!e.relatedTarget) hide();
    };

    document.addEventListener("mouseout", leftWindow);
    document.addEventListener("mousedown", hide);
    document.addEventListener("mouseover", show);
    document.addEventListener("scroll", hide, true);
    return () => {
      window.clearTimeout(timer);
      document.removeEventListener("mouseout", leftWindow);
      document.removeEventListener("mousedown", hide);
      document.removeEventListener("mouseover", show);
      document.removeEventListener("scroll", hide, true);
    };
  }, []);

  if (!tip) return null;
  return (
    <div className={`tooltip ${tip.below ? "below" : "above"}`} role="tooltip"
      style={{ left: tip.x, top: tip.y, maxWidth: WIDTH }}>
      {tip.text}
    </div>
  );
}
