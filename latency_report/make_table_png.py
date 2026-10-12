"""Draw the latency table as an IEEE-style PNG. Same numbers as latency_table.tex."""

import textwrap
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).parent
plt.rcParams["font.family"] = "serif"
plt.rcParams["font.serif"] = ["Times New Roman", "Times", "DejaVu Serif"]

HEADERS = [("(a)", "Baseline:", "Jev + Claude,", "3 Hz"), ("(b)", "Transcript", "skips gate", "cooldown"),
           ("(c)", "10 Hz tick,", "Groq", "replies"), ("(d)", "Instant", "publish", ""),
           ("(e)", "Streaming", "speech,", "warm-up"), ("(f)", "Groq", "Whisper,", "0.8 s pause"),
           ("(g)", "0.65 s", "pause,", "120B model")]
D = "–"
ROWS = [
    ("Audio node, total", ["1.30", "1.63", "1.50", "1.27", "1.28", "1.37", "1.28"], False, 0),
    ("Silence check", [D, D, D, "0.53", "0.53", "0.90", "0.68"], False, 1),
    ("Transcription", [D, D, D, "0.74", "0.75", "0.47", "0.60"], False, 1),
    ("Publish wait", [D, D, D, "0.00", "0.00", "0.00", "0.00"], False, 1),
    ("Transfer to decision node", ["0.45", "0.28", "0.23", "0.00", "0.00", "0.07", "0.00"], False, 0),
    ("Gate wait", ["1.65", "0.00", "0.00", "0.00", "0.00", "0.00", "0.00"], False, 0),
    ("Decision (Jev)", ["1.05", "0.27", "0.25", "0.25", "0.28", "0.24", "0.24"], False, 0),
    ("Reply text (LLM)", ["1.70", "1.62", "0.45", "0.52", "0.58", "0.76", "0.68"], False, 0),
    ("Speech", ["1.40", "1.50", "1.35", "1.21", "0.25", "0.23", "0.23"], False, 0),
    None,
    ("Total, mean", ["7.85", "4.98", "3.95", "3.16", "2.35", "2.61", "2.42"], True, 0),
    ("Total, median", ["7.85", "4.95", "3.90", "2.93", "2.27", "2.60", "2.37"], False, 0),
]
NOTES = ("Total is the time from the end of the person's speech to the start of the robot's voice. "
         "Each column adds one change to the column on its left. Values are means over 2 to 12 replies "
         "per configuration, measured on the robot on October 12, 2026. Columns (a)–(c) come from a "
         "timing log with 0.1 s resolution; columns (d)–(g) come from a per-step trace with 0.01 s "
         f"resolution. {D}: not measured separately. Speech excludes replies that played a cached line; "
         "from (e) on, it is the time until the first sound. Column (d) includes one 6.78 s reply with "
         "1.35 s not attributed to any step. Column (g) pools two runs and includes one 1.40 s "
         "transcription. In column (f), the reply model was not recorded.")

W, MARGIN = 7.16, 0.12
LABEL_W = 1.75
COL_W = (W - 2 * MARGIN - LABEL_W) / 7
ROW_H, HEAD_LINE = 0.175, 0.135
notes = textwrap.wrap(NOTES, 162)

y = 0.12
caption_y = [y, y + 0.17]
y += 0.40
top_rule = y
head_y = [y + 0.12 + i * HEAD_LINE for i in range(4)]
y = head_y[-1] + 0.10
mid_rule = y
rows_y, total_rule = [], None
for row in ROWS:
    if row is None:
        y += 0.10
        total_rule = y
        y += 0.01
        continue
    y += ROW_H
    rows_y.append(y)
y += 0.07
bottom_rule = y
notes_y = [y + 0.16 + i * 0.125 for i in range(len(notes))]
H = notes_y[-1] + 0.12

fig = plt.figure(figsize=(W, H), dpi=300)
ax = fig.add_axes([0, 0, 1, 1])
ax.set_xlim(0, W)
ax.set_ylim(H, 0)
ax.axis("off")

ax.text(W / 2, caption_y[0], "TABLE I", ha="center", va="center", fontsize=9)
ax.text(W / 2, caption_y[1], "RESPONSE LATENCY OF THE LIVE INITIATOR ON THE ROBOT, BY PIPELINE STEP (SECONDS)",
        ha="center", va="center", fontsize=7.6)

x0, x1 = MARGIN, W - MARGIN
for yy, lw in ((top_rule, 0.9), (mid_rule, 0.5), (total_rule, 0.5), (bottom_rule, 0.9)):
    ax.plot([x0, x1], [yy, yy], color="black", lw=lw)

col_x = [x0 + LABEL_W + COL_W * (i + 0.5) for i in range(7)]
for cx, lines in zip(col_x, HEADERS):
    for yy, text in zip(head_y, lines):
        ax.text(cx, yy, text, ha="center", va="center", fontsize=7.6)

rows = [r for r in ROWS if r is not None]
for yy, (label, values, bold, indent) in zip(rows_y, rows):
    weight = "bold" if bold else "normal"
    ax.text(x0 + 0.16 * indent, yy, label, ha="left", va="center", fontsize=8, weight=weight)
    for cx, v in zip(col_x, values):
        ax.text(cx, yy, v, ha="center", va="center", fontsize=8, weight=weight)

for yy, line in zip(notes_y, notes):
    ax.text(x0, yy, line, ha="left", va="center", fontsize=6.8)

out = HERE / "latency_table.png"
fig.savefig(out, dpi=300, facecolor="white")
print(out)
