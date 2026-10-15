# Study: does the LLM choose good moments to speak?

The question: when an LLM gets only a structured description of the scene, how
appropriate do people find its decisions about when to start a conversation?

On this branch, the robot runs without rules by default. The LLM gets the scene, the six rubric scales, and
the four actions, and no social rules. Each participant acts out task cards. After
each trial, the participant rates what the robot did. `analyze.py` matches each rating
to the robot's logged decisions and makes the tables for the paper.

## What the robot is told, and what stays in code

| Part | Without rules (the default on this branch; `--rules` turns them back on) |
|---|---|
| LLM prompt | The scene JSON, the field guide, the six rubric scales, the actions. No R1 to R6. Jev gets no `rule_fired` question. |
| Gate (before the LLM) | A fixed clock: the LLM is asked every 1 s (`--every`), and a call that takes over 2 s is dropped (`--timeout`), with or without a person in view, whether or not the scene changed. A new sentence from the person asks at once. The LLM is also asked while the robot talks; it sees `is_speaking: true`. No settle check, no 1.5 m limit, no "gave up". |
| Post-filter (after the LLM) | Practical checks only: nobody there, the robot is talking, a reply with no transcript, the person is mid-sentence. No R1 or R2 blocks. If the LLM chooses to speak while a line is playing, the second line is not played, and the log keeps the LLM's choice (`analyze.py` counts these). |
| Session handling | The robot talks in the background, so the LLM keeps deciding. `last_spoke_s_ago` counts from the start of the line. 5 s out of view ends the conversation. Unanswered robot lines do not end the conversation; the LLM sees `consecutive_no_response` and decides (with `--rules`, two unanswered lines end `engaged`). |

Report all of these in the method section.

## Before the session

- Put tape on the floor at about 1 m and 2 m in front of the camera.
- Clear the area. Only the participant (and a partner, for `chat_with_partner`) is in view.
- Use participant codes (P01, P02, ...). Never type a name into the tool.

## Run it: three terminals on flexo

**Terminal 1: sensors**

```bash
python3 ~/fri2_f26/fusion/fusion_publisher.py --no-base
```

**Terminal 2: the robot, with no rules**

```bash
cd ~/fri2_f26/conversation_initiator/mvp && python3 live_node.py --speak --provider jev --turn-off
```

Check that it prints `rules: off: scene only, the model decides, asked every 1 s`.
`--no-base` and `--turn-off` keep the robot still. Turning is one more thing that can
change how people react, so keep it off for every participant.

**Terminal 3: the trials**

```bash
python3 ~/fri2_f26/study/run_trials.py --participant P01
```

For each trial:

1. Show the card on the screen to the participant only.
2. Press Enter when the participant starts.
3. Press Enter when the trial ends, after about 25 s, or when the person has left.
4. The participant answers two questions: how appropriate the robot was (1 to 5), and which of six outcomes fits best.
5. The participant leaves the camera view. The tool counts down 8 s, so the robot starts the next trial fresh.

Defaults: the tasks `walk_past`, `want_to_talk`, and `busy_nearby`, two times each, in a random order that depends on the participant code. Add `chat_with_partner` when two people are there:

```bash
python3 ~/fri2_f26/study/run_trials.py --participant P02 --tasks walk_past,want_to_talk,busy_nearby,chat_with_partner
```

If the tool stops, run the same command again. It continues at the next trial.

## The task cards

| Task | Card | The card intends |
|---|---|---|
| `walk_past` | Walk past at a normal pace, about 2 m away. Do not stop or look at the robot. | silence |
| `want_to_talk` | Walk up, stop about 1 m away, look at the robot. If it speaks, ask one question. | speech |
| `busy_nearby` | Stand about 1 m away and look at your phone the whole time. | silence |
| `chat_with_partner` | Stand about 1.5 m away with a partner and talk to each other. | silence |

The card's intent is one measure. The participant's own rating is the main measure,
because the person in the interaction judges what is polite.

## After the study

```bash
python3 ~/fri2_f26/study/analyze.py
```

It reads `study/data/*.csv` and `conversation_initiator/mvp/live_logs/*.jsonl`, and
writes `study/results/`:

- `summary.md`: the tables. Overall, by task, errors, the LLM's rubric scores by task, speed, and whether participants saw what the log shows.
- `trials.csv`: one row per trial.
- `by_task.png`, `participant_choice.png`: charts, when matplotlib is installed (`pip install --user matplotlib`).

Run it on flexo. The trial times and the log times must come from the same clock.

## Privacy

`study/data/` and `study/results/` stay out of git. The logs hold transcripts of what
participants said. Check comments and transcripts before you share any file.
