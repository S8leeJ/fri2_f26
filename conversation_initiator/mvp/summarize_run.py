#!/usr/bin/env python3
"""Print one run of live_logs as one short line per LLM call, to paste or share.

    python3 summarize_run.py                 # the last run in the newest live_logs file
    python3 summarize_run.py --run 3 --log live_logs/2026-10-19.jsonl

Columns: seconds since the first call; the person (distance, F = facing,
gaze seconds, motion, dwell seconds) or "-" for nobody; talk = speech in the
room; eng = engaged; spk = the robot talks; the LLM's action, and the final
action when the post-filter changed it; call ms; the six rubric scores in
schema order; the category; confidence; what was heard and said.
TRACE lines give the seconds from the end of a sentence to the reply.
"""

from __future__ import annotations

import argparse
import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
RUBRIC = ("invitation", "interruption_cost", "urgency", "redundancy", "ambient_fit", "addressivity")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--log", help="a live_logs/<date>.jsonl file; the newest by default")
    ap.add_argument("--run", type=int, help="the run number; the last run in the file by default")
    args = ap.parse_args()

    path = pathlib.Path(args.log) if args.log else sorted((HERE / "live_logs").glob("*.jsonl"))[-1]
    rows = []
    with open(path) as f:
        for line in f:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    run = args.run or [r for r in rows if "run_start" in r][-1]["run"]
    start = next((r for r in rows if r.get("run_start") and r["run"] == run), {})
    print(f"# {path.name} run {run}, started {start.get('run_start')}, rules {start.get('rules')}")
    print("# s | person: dist F gaze motion dwell | talk eng spk | action (final) ms | "
          "rubric inv,cost,urg,red,amb,addr | category | conf | heard / says")

    t0 = None
    for r in rows:
        if r.get("run") != run or "run_start" in r:
            continue
        if "trace" in r:
            when = f"{r['t'] - t0:.1f}" if t0 else "?"
            print(f"{when} TRACE reply {r['trace'].get('total')} s")
            continue
        if "context" not in r:
            continue
        c, x = r["context"], r["result"]
        t0 = t0 if t0 is not None else c["t"]
        p = c.get("target") or {}
        robot = c.get("robot") or {}
        d = x.get("decision") or {}
        rubric = d.get("rubric") or {}
        person = (f"{p.get('distance_m')} {'F' if p.get('facing_robot') else 'notF'} "
                  f"{p.get('gaze_at_robot_s', '')} {p.get('motion', '')} {p.get('dwell_s', '')}") if p else "-"
        flags = " ".join(name for name, on in (("talk", (c.get("ambient") or {}).get("speech_now")),
                                               ("eng", robot.get("engaged")),
                                               ("spk", robot.get("is_speaking"))) if on)
        action = x.get("action_raw") or "-"
        if x.get("blocked_by"):
            action += f" ({x.get('action_final')}: {x['blocked_by']})"
        heard = ((p.get("speech") or {}).get("partial_transcript"))
        says = (x.get("speech") or {}).get("text")
        print(" | ".join([
            f"{c['t'] - t0:.1f}", person, flags, f"{action} {round(x.get('ms1') or 0)}",
            ",".join(str(rubric.get(k, "")) for k in RUBRIC), d.get("category", ""),
            str(d.get("confidence", "")),
            " ".join(filter(None, [f"HEARD {heard!r}" if heard else "", f"SAYS {says!r}" if says else "",
                                   f"ERROR {x['error']}" if x.get("error") else ""])),
        ]))


if __name__ == "__main__":
    main()
