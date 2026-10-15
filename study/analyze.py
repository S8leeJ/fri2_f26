#!/usr/bin/env python3
"""Match study trials to the robot's logged decisions and summarize the results.

    python3 study/analyze.py
    python3 study/analyze.py --data DIR --logs DIR --out DIR

Inputs:
    study/data/*.csv                              one row per trial, from run_trials.py
    conversation_initiator/mvp/live_logs/*.jsonl  every LLM call, run starts, reply timings

Outputs in study/results/:
    trials.csv   one row per trial: the card, what the robot did, and the participant's rating
    summary.md   the tables for the paper
    *.png        charts, when matplotlib is installed

Run it where both inputs are, normally on flexo. The trial times and the log
times must come from the same clock.
"""

from __future__ import annotations

import argparse
import csv
import json
import pathlib
import statistics
from collections import Counter, defaultdict

REPO = pathlib.Path(__file__).resolve().parent.parent
SPEAKS = ("greet", "respond")
RUBRIC = ["invitation", "interruption_cost", "urgency", "redundancy", "ambient_fit", "addressivity"]
OUTCOME_SHORT = {"1": "spoke, right time", "2": "spoke too early", "3": "spoke too late",
                 "4": "spoke, should not have", "5": "silent, right", "6": "silent, should have spoken"}


def load_trials(data: pathlib.Path):
    trials = []
    for path in sorted(data.glob("*.csv")):
        with open(path, newline="") as f:
            for row in csv.DictReader(f):
                row["start_t"], row["end_t"] = float(row["start_t"]), float(row["end_t"])
                row["appropriate"] = int(row["appropriate"])
                trials.append(row)
    return trials


def load_logs(logs: pathlib.Path):
    """Decisions and reply timings from every daily log, in time order."""
    decisions, traces = [], []
    for path in sorted(logs.glob("*.jsonl")):
        rules = {}
        with open(path) as f:
            for line in f:
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if "run_start" in rec:
                    rules[rec["run"]] = rec.get("rules", True)
                elif "result" in rec:
                    res = rec["result"]
                    decision = res.get("decision") or {}
                    decisions.append({
                        "t": float(res.get("t") or rec["context"].get("t") or 0.0),
                        "action": res.get("action_final", "remain_silent"),
                        "action_raw": res.get("action_raw"),
                        "blocked_by": res.get("blocked_by"),
                        "error": res.get("error"),
                        "rubric": decision.get("rubric"),
                        "ms1": res.get("ms1"),
                        "ms2": res.get("ms2"),
                        "says": (res.get("speech") or {}).get("text"),
                        "rules": res.get("rules", rules.get(rec.get("run"), True)),
                    })
                elif "trace" in rec:
                    traces.append({"t": float(rec["t"]), **rec["trace"]})
    decisions.sort(key=lambda d: d["t"])
    traces.sort(key=lambda d: d["t"])
    return decisions, traces


def match(trials, decisions, traces, grace):
    rows = []
    for tr in trials:
        lo, hi = tr["start_t"], tr["end_t"] + grace
        inside = [d for d in decisions if lo <= d["t"] <= hi]
        spoken = [d for d in inside if d["action"] in SPEAKS]
        modes = {("rules" if d["rules"] else "no_rules") for d in inside}
        robot_spoke = bool(spoken)
        perceived_spoke = tr["outcome"] in ("1", "2", "3", "4")
        rows.append({
            **{k: tr[k] for k in ("participant", "condition", "trial", "task", "expected",
                                  "appropriate", "outcome", "outcome_text", "comment")},
            "duration_s": round(tr["end_t"] - tr["start_t"], 1),
            "llm_calls": len(inside),
            "spoke_over": sum(1 for d in inside if d["blocked_by"] == "self_speaking"
                              and d["action_raw"] in SPEAKS),
            "logged_mode": "/".join(sorted(modes)) or "no call",
            "robot_spoke": robot_spoke,
            "first_speech_s": round(spoken[0]["t"] - tr["start_t"], 2) if spoken else None,
            "first_action": inside[0]["action"] if inside else None,
            "actions": " ".join(d["action"] for d in inside),
            "first_says": spoken[0]["says"] if spoken else None,
            "matched_card": robot_spoke == (tr["expected"] == "speak"),
            "rated_appropriate": tr["appropriate"] >= 4,
            "participant_says_right": tr["outcome"] in ("1", "5"),
            "perception_agrees": perceived_spoke == robot_spoke,
            "first_rubric": inside[0]["rubric"] if inside else None,
            "decide_ms": [d["ms1"] for d in inside if d["ms1"] is not None],
            "reply_s": [x["total"] for x in traces if lo <= x["t"] <= hi and "total" in x],
        })
    return rows


def pct(n, d):
    return f"{100 * n / d:.0f}% ({n}/{d})" if d else "–"


def mean_sd(values):
    if not values:
        return "–"
    if len(values) == 1:
        return f"{values[0]:.2f}"
    return f"{statistics.mean(values):.2f} ± {statistics.stdev(values):.2f}"


def quantile(values, q):
    values = sorted(values)
    return values[min(len(values) - 1, max(0, round(q * (len(values) - 1))))]


def table(head, body):
    lines = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    lines += ["| " + " | ".join(str(c) for c in row) + " |" for row in body]
    return "\n".join(lines)


def summarize(rows):
    out = ["# Study results", ""]
    participants = sorted({r["participant"] for r in rows})
    out.append(f"{len(rows)} trials, {len(participants)} participants: {', '.join(participants)}.")
    out.append("")

    out += ["## 1. Overall, by condition", ""]
    body = []
    for cond in sorted({r["condition"] for r in rows}):
        rs = [r for r in rows if r["condition"] == cond]
        body.append([cond, len(rs), pct(sum(r["matched_card"] for r in rs), len(rs)),
                     pct(sum(r["rated_appropriate"] for r in rs), len(rs)),
                     mean_sd([r["appropriate"] for r in rs]),
                     pct(sum(r["participant_says_right"] for r in rs), len(rs))])
    out.append(table(["Condition", "Trials", "Robot matched the card", "Rated appropriate (4–5)",
                      "Rating, mean ± SD (1–5)", "Participant chose 'right'"], body))
    out.append("")

    out += ["## 2. By task", ""]
    body = []
    for (cond, task), rs in sorted(group(rows, "condition", "task").items()):
        outcomes = Counter(r["outcome"] for r in rs)
        body.append([cond, task, rs[0]["expected"], len(rs),
                     pct(sum(r["robot_spoke"] for r in rs), len(rs)),
                     pct(sum(r["matched_card"] for r in rs), len(rs)),
                     mean_sd([r["appropriate"] for r in rs]),
                     "; ".join(f"{OUTCOME_SHORT[k]} {v}" for k, v in sorted(outcomes.items()))])
    out.append(table(["Condition", "Task", "Card intends", "Trials", "Robot spoke",
                      "Matched", "Rating (1–5)", "Participant's choice"], body))
    out.append("")

    out += ["## 3. Errors", ""]
    false_starts = [r for r in rows if r["expected"] == "silent" and r["robot_spoke"]]
    missed = [r for r in rows if r["expected"] == "speak" and not r["robot_spoke"]]
    out.append(f"- Spoke when the card intended silence: {len(false_starts)}"
               + (f", mean rating {mean_sd([r['appropriate'] for r in false_starts])}" if false_starts else ""))
    out.append(f"- Stayed silent when the card intended speech: {len(missed)}"
               + (f", mean rating {mean_sd([r['appropriate'] for r in missed])}" if missed else ""))
    out.append(f"- The LLM chose to speak while the robot was already talking (the line was not played): "
               f"{sum(r['spoke_over'] for r in rows)} times")
    no_call = [r for r in rows if r["llm_calls"] == 0]
    out.append(f"- Trials with no LLM call (nobody detected, or the gate skipped all): {len(no_call)}")
    out.append("")

    out += ["## 4. How the LLM scored each task (first call in the trial, mean)", ""]
    body = []
    for (cond, task), rs in sorted(group(rows, "condition", "task").items()):
        scored = [r["first_rubric"] for r in rs if r["first_rubric"]]
        body.append([cond, task, len(scored)]
                    + [f"{statistics.mean(s[d] for s in scored):.1f}" if scored else "–" for d in RUBRIC])
    out.append(table(["Condition", "Task", "Calls"] + RUBRIC, body))
    out.append("")

    out += ["## 5. Speed", ""]
    decide = [ms for r in rows for ms in r["decide_ms"]]
    reply = [s for r in rows for s in r["reply_s"]]
    greet = [r["first_speech_s"] for r in rows if r["task"] == "want_to_talk" and r["first_speech_s"] is not None]
    body = []
    if decide:
        body.append(["LLM decision (ms)", len(decide), f"{statistics.median(decide):.0f}", f"{quantile(decide, 0.9):.0f}"])
    if reply:
        body.append(["End of speech to robot voice (s)", len(reply), f"{statistics.median(reply):.2f}", f"{quantile(reply, 0.9):.2f}"])
    if greet:
        body.append(["Trial start to greeting, want_to_talk (s)", len(greet), f"{statistics.median(greet):.1f}", f"{quantile(greet, 0.9):.1f}"])
    out.append(table(["Measure", "n", "Median", "90th percentile"], body) if body else "No timings in the logs.")
    out.append("")

    out += ["## 6. Did the participant see what the log shows?", ""]
    out.append("Participant said the robot spoke (choices 1–4) or stayed silent (5–6), "
               f"compared with the log: agree in {pct(sum(r['perception_agrees'] for r in rows), len(rows))}.")
    out.append("")
    return "\n".join(out)


def group(rows, *keys):
    groups = defaultdict(list)
    for r in rows:
        groups[tuple(r[k] for k in keys)].append(r)
    return groups


def charts(rows, out: pathlib.Path):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return []
    tasks = sorted({r["task"] for r in rows})
    made = []

    fig, ax = plt.subplots(figsize=(7, 3.5))
    width = 0.38
    x = range(len(tasks))
    matched = [100 * statistics.mean(r["matched_card"] for r in rows if r["task"] == t) for t in tasks]
    rated = [100 * statistics.mean(r["rated_appropriate"] for r in rows if r["task"] == t) for t in tasks]
    ax.bar([i - width / 2 for i in x], matched, width, label="Robot matched the card", color="#2563C9")
    ax.bar([i + width / 2 for i in x], rated, width, label="Participant rated it appropriate (4–5)", color="#E07A2E")
    ax.set_xticks(list(x), tasks)
    ax.set_ylim(0, 100)
    ax.set_ylabel("% of trials")
    ax.legend(frameon=False, fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=2)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(out / "by_task.png", dpi=200)
    made.append("by_task.png")

    fig, ax = plt.subplots(figsize=(7, 3.5))
    bottom = [0] * len(tasks)
    colors = ["#2563C9", "#8FB8FF", "#C9D8F5", "#E07A2E", "#5B8C5A", "#B5BCC6"]
    for code, color in zip(sorted(OUTCOME_SHORT), colors):
        counts = [sum(1 for r in rows if r["task"] == t and r["outcome"] == code) for t in tasks]
        ax.bar(tasks, counts, bottom=bottom, label=OUTCOME_SHORT[code], color=color)
        bottom = [b + c for b, c in zip(bottom, counts)]
    ax.set_ylabel("Trials")
    ax.legend(frameon=False, fontsize=7, loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=3)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(out / "participant_choice.png", dpi=200)
    made.append("participant_choice.png")
    return made


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--data", type=pathlib.Path, default=REPO / "study" / "data")
    ap.add_argument("--logs", type=pathlib.Path, default=REPO / "conversation_initiator" / "mvp" / "live_logs")
    ap.add_argument("--out", type=pathlib.Path, default=REPO / "study" / "results")
    ap.add_argument("--grace", type=float, default=2.0,
                    help="seconds after a trial ends that still count for it")
    args = ap.parse_args()

    trials = load_trials(args.data)
    if not trials:
        raise SystemExit(f"No trials in {args.data}")
    decisions, traces = load_logs(args.logs)
    rows = match(trials, decisions, traces, args.grace)

    args.out.mkdir(parents=True, exist_ok=True)
    fields = [k for k in rows[0] if k not in ("first_rubric", "decide_ms", "reply_s")]
    with open(args.out / "trials.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields + RUBRIC, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({**r, **(r["first_rubric"] or {})})
    summary = summarize(rows)
    (args.out / "summary.md").write_text(summary, encoding="utf-8")
    made = charts(rows, args.out)
    print(summary)
    print(f"Wrote {args.out / 'trials.csv'}, {args.out / 'summary.md'}"
          + (", " + ", ".join(made) if made else " (no charts: matplotlib is not installed)"))


if __name__ == "__main__":
    main()
