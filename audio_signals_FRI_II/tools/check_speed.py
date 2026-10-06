# Goal: find out whether the machine can keep up. Times each stage against
# the budget, which is one block of audio: 128 ms.
#
#   python3 tools/check_speed.py
#
# Run this when "input overflow" appears. Overflow means audio arrived
# faster than it was consumed, so blocks were lost before anything saw
# them. Either the processing is too slow, or the audio thread is being
# starved by something else on the machine.

import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from audio_context import loudness, vad
from audio_context.config import CONFIG
from audio_context.frames import Buffer
from audio_context.processor import Result
from audio_context import frames as fr


def main():
    rate = CONFIG["sample_rate"]
    n = CONFIG["block_samples"]
    budget = n / rate * 1000

    print(f"\n  budget is {budget:.0f} ms per block, which is how often audio "
          f"arrives.\n  Anything close to that will overflow.\n")

    rng = np.random.default_rng(3)
    block = type("B", (), {"t": time.time(),
                           "samples": (rng.standard_normal(n) * 0.02).astype(np.float32)})()

    print("  loading the voice detector...")
    vad.warm_up()

    def timed(label, fn, runs=40):
        fn()                                    # warm
        t0 = time.perf_counter()
        for _ in range(runs):
            fn()
        ms = (time.perf_counter() - t0) / runs * 1000
        bar = "#" * int(min(ms / budget, 1.0) * 30)
        print(f"  {label:<22}{ms:>7.1f} ms  {ms/budget:>5.0%}  {bar}")
        return ms

    total = 0.0
    total += timed("loudness", lambda: loudness.from_block(block))
    total += timed("voice detection", lambda: vad.from_block(block))

    # The stores are the part that touches disk, so they are the most
    # likely thing to be slow on a busy machine.
    buf = Buffer(CONFIG["buffer_dir"], CONFIG["buffer_seconds"],
                 CONFIG["frame_samples"] / rate)
    db = loudness.from_block(block)
    voice = vad.from_block(block)
    t = time.time()

    def store():
        nonlocal t
        t += n / rate
        bg, sp = fr.from_result(Result(t, db, voice),
                                CONFIG["frame_samples"] / rate)
        buf.add(bg, sp)

    total += timed("writing to the stores", store, runs=40)
    buf.close()

    print(f"\n  {'total':<22}{total:>7.1f} ms  {total/budget:>5.0%}")
    if total > budget * 0.7:
        print(f"\n  Too close to the budget. Overflow is likely.")
    elif total > budget * 0.4:
        print(f"\n  Comfortable, but little headroom if the machine gets busy.")
    else:
        print(f"\n  Plenty of headroom. If overflow still appears, the audio "
              f"thread is\n  being starved by something else on the machine "
              f"rather than by this code.")
    return 0


if __name__ == "__main__":
    sys.exit(main())