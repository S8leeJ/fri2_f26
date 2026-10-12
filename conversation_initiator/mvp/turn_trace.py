"""Time each step from the end of a person's speech to the robot's reply.

    tracer = Tracer(path)
    tracer.add(marks, ms1, ms2, tts_s, done)   # one reply; returns a one-line summary
    tracer.summary()                           # median and max of each step

marks holds wall times from one clock (flexo): speech_end, and when present
closed, stt_start, stt_done, built (audio node), arrived, seen, asked (live node).
"""

from __future__ import annotations

import json
import pathlib
import statistics
from typing import Dict, List, Optional, Tuple

# Each step runs from the first mark to the second.
MARKED = (
    ("close", "speech_end", "closed"),     # silence wait before the utterance closes
    ("stt", "closed", "stt_done"),         # Whisper, with any queue wait
    ("publish", "stt_done", "built"),      # audio node 1 Hz timer
    ("fusion", "built", "arrived"),        # ROS hops and the fusion 10 Hz timer
    ("tick", "arrived", "seen"),           # live node tick, or a call in progress
    ("gate", "seen", "asked"),             # gate cooldown
)


def steps(marks: Dict[str, float], ms1: float, ms2: Optional[float],
          tts_s: Optional[float]) -> List[Tuple[str, float]]:
    out = []
    if "closed" not in marks and "seen" in marks:
        # The audio node sent no trace, so only the total wait is known.
        out.append(("heard", marks["seen"] - marks["speech_end"]))
        if "asked" in marks:
            out.append(("gate", marks["asked"] - marks["seen"]))
    else:
        out += [(name, marks[b] - marks[a]) for name, a, b in MARKED if a in marks and b in marks]
    out.append(("decide", ms1 / 1000))
    if ms2:
        out.append(("line", ms2 / 1000))
    if tts_s is not None:
        out.append(("tts", tts_s))
    return out


class Tracer:
    def __init__(self, path: pathlib.Path):
        self.path = path
        self.turns: List[Dict[str, float]] = []

    def add(self, marks: Dict[str, float], ms1: float, ms2: Optional[float],
            tts_s: Optional[float], done: float) -> str:
        """done is when the robot starts to talk, or when its line is ready in a dry run."""
        row = dict(steps(marks, ms1, ms2, tts_s))
        row["total"] = done - marks["speech_end"]
        self.turns.append(row)
        with open(self.path, "a") as f:
            f.write(json.dumps({"marks": marks, "steps": {k: round(v, 3) for k, v in row.items()}}) + "\n")
        parts = "  ".join(f"{k} {v:.2f}" for k, v in row.items() if k != "total")
        return f"turn {len(self.turns)}: {row['total']:.2f} s  |  {parts}"

    def summary(self) -> str:
        if not self.turns:
            return "trace: no replies this session"
        names = list(dict.fromkeys(k for row in self.turns for k in row))
        lines = [f"trace: {len(self.turns)} replies, seconds (median / max), log {self.path}"]
        for name in names:
            values = [row[name] for row in self.turns if name in row]
            lines.append(f"  {name:<8} {statistics.median(values):5.2f} / {max(values):5.2f}")
        return "\n".join(lines)
