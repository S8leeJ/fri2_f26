#!/usr/bin/env python3
"""Run study trials and record what each participant thought of the robot.

Run it on flexo in a third terminal, while fusion_publisher.py and live_node.py run:

    python3 ~/fri2_f26/study/run_trials.py --participant P01

It shows one task card at a time. The experimenter presses Enter when the
participant starts and again when the trial ends. The participant then rates
what the robot did. Each trial is one row in study/data/<participant>.csv.
The start and end times use flexo's clock, so analyze.py can match each trial
to the robot's logged decisions. Use participant codes, never names.
"""

from __future__ import annotations

import argparse
import csv
import datetime
import pathlib
import random
import sys
import time

DATA = pathlib.Path(__file__).resolve().parent / "data"

# name: (task card, what the card intends the robot to do)
TASKS = {
    "walk_past": ("Walk past the robot at a normal pace, about 2 m in front of it. "
                  "Do not stop, and do not look at it.", "silent"),
    "want_to_talk": ("You want to ask the robot something. Walk up, stop about 1 m in front of it, "
                     "and look at it. If it speaks to you, ask it one question.", "speak"),
    "busy_nearby": ("Stand about 1 m from the robot and look at your phone the whole time, "
                    "as if you are busy. Do not look at the robot.", "silent"),
    "chat_with_partner": ("With your partner, stand about 1.5 m from the robot and talk to each "
                          "other. Do not look at the robot.", "silent"),
}

OUTCOMES = {
    "1": "spoke at the right moment",
    "2": "spoke too early",
    "3": "spoke too late",
    "4": "spoke, but should have stayed silent",
    "5": "stayed silent, and that was right",
    "6": "stayed silent, but should have spoken",
}

FIELDS = ["participant", "condition", "trial", "task", "expected", "start_t", "end_t",
          "duration_s", "appropriate", "outcome", "outcome_text", "comment", "recorded_at"]


def ask(prompt: str, allowed: str) -> str:
    while True:
        answer = input(prompt).strip()
        if answer in allowed and len(answer) == 1:
            return answer
        print(f"  Type one of: {' '.join(allowed)}")


def countdown(seconds: int, text: str) -> None:
    for left in range(seconds, 0, -1):
        print(f"\r{text} {left:2d} s ", end="", flush=True)
        time.sleep(1)
    print("\r" + " " * (len(text) + 8) + "\r", end="")


def trial_order(tasks, reps, seed):
    order = [t for t in tasks for _ in range(reps)]
    random.Random(seed).shuffle(order)
    return order


def done_trials(path: pathlib.Path) -> int:
    if not path.exists():
        return 0
    with open(path, newline="") as f:
        return sum(1 for _ in csv.DictReader(f))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--participant", required=True, help="a code such as P01, never a name")
    ap.add_argument("--condition", default="no_rules",
                    help="a label for the live_node.py mode; use no_rules with --no-rules")
    ap.add_argument("--tasks", default="walk_past,want_to_talk,busy_nearby",
                    help="comma list from: " + ", ".join(TASKS) + " (chat_with_partner needs 2 people)")
    ap.add_argument("--reps", type=int, default=2, help="times each task runs")
    ap.add_argument("--seed", default=None, help="order seed; the participant code by default")
    ap.add_argument("--trial-seconds", type=int, default=25, help="suggested trial length")
    ap.add_argument("--reset-seconds", type=int, default=8,
                    help="time out of view between trials; the robot ends a visit after 5 s")
    args = ap.parse_args()

    tasks = [t.strip() for t in args.tasks.split(",") if t.strip()]
    unknown = [t for t in tasks if t not in TASKS]
    if unknown:
        sys.exit(f"Unknown task: {', '.join(unknown)}. Known: {', '.join(TASKS)}")

    DATA.mkdir(parents=True, exist_ok=True)
    path = DATA / f"{args.participant}.csv"
    order = trial_order(tasks, args.reps, args.seed or args.participant)
    first = done_trials(path)
    if first >= len(order):
        sys.exit(f"{path} already has {first} trials, which is all {len(order)} of them.")
    if first:
        print(f"{path} already has {first} trials. Continuing at trial {first + 1}.")

    new_file = not path.exists()
    with open(path, "a", newline="") as f:
        out = csv.DictWriter(f, fieldnames=FIELDS)
        if new_file:
            out.writeheader()
        for number in range(first + 1, len(order) + 1):
            task = order[number - 1]
            card, expected = TASKS[task]
            print("\n" + "=" * 70)
            print(f"Trial {number} of {len(order)} · {args.participant} · condition {args.condition}")
            print("Show this card to the participant only:\n")
            print(f"    {card}\n")
            key = input("Press Enter when the participant starts (s = skip, q = quit): ").strip().lower()
            if key == "q":
                break
            if key == "s":
                continue
            start = time.time()
            input(f"Running. About {args.trial_seconds} s. Press Enter when the trial ends: ")
            end = time.time()

            print("\nParticipant: how appropriate was what the robot did?")
            appropriate = ask("  1 = very inappropriate ... 5 = very appropriate: ", "12345")
            print("Participant: which fits best?")
            for code, text in OUTCOMES.items():
                print(f"  {code}  The robot {text}")
            outcome = ask("  Choice: ", "".join(OUTCOMES))
            comment = input("Comment (optional, no names): ").strip()

            out.writerow({"participant": args.participant, "condition": args.condition,
                          "trial": number, "task": task, "expected": expected,
                          "start_t": round(start, 3), "end_t": round(end, 3),
                          "duration_s": round(end - start, 1), "appropriate": appropriate,
                          "outcome": outcome, "outcome_text": OUTCOMES[outcome], "comment": comment,
                          "recorded_at": datetime.datetime.now().isoformat(timespec="seconds")})
            f.flush()
            if number < len(order):
                print("\nThe participant leaves the camera view now.")
                countdown(args.reset_seconds, "Reset, out of view:")

    print(f"\nSaved {done_trials(path)} trials in {path}")


if __name__ == "__main__":
    main()
