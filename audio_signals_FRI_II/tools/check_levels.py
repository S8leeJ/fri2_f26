# Goal: work out why the level looks lower here than in another meter.
#
#   python tools/check_levels.py
#   python tools/check_levels.py --seconds 10
#
# Reports each channel separately, before anything is mixed to mono, plus
# what the device is doing. Three things usually explain a gap:
#
#   1  a browser meter has automatic gain control on, and this does not.
#      Browsers enable AGC by default in getUserMedia. Nothing here uses
#      it, because AGC changes the gain as the room changes, which would
#      make noise_floor_db meaningless.
#
#   2  the device reports several channels and only one carries signal.
#      Averaging to mono then costs 6 dB for two channels, 12 dB for four.
#      This prints each channel, so a dead one is obvious.
#
#   3  the capture volume is low. On Linux check `alsamixer` with F4, or
#      `pactl list sources`. On Windows, Sound settings, the input device,
#      then Input volume.

import argparse
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from audio_context.capture import resolve_device
from audio_context.config import CONFIG


def db(x):
    rms = float(np.sqrt(np.mean(np.square(x, dtype=np.float64))))
    return 20.0 * np.log10(rms + 1e-12)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=6.0)
    args = ap.parse_args()

    import sounddevice as sd

    device = resolve_device(CONFIG["input_device"])
    info = sd.query_devices(device if device is not None else sd.default.device[0])
    channels = CONFIG["input_channels"] or int(info["max_input_channels"])
    rate = int(CONFIG["capture_sample_rate"] or info["default_samplerate"])

    print(f"\n  device    {info['name']}")
    print(f"  backend   {sd.query_hostapis()[info['hostapi']]['name']}")
    print(f"  channels  {channels}")
    print(f"  rate      {rate} Hz")
    if channels > 1:
        print(f"\n  Note: {channels} channels get averaged to mono. If only one "
              f"carries\n  signal, that costs "
              f"{20*np.log10(channels):.0f} dB.")

    print(f"\n  Talk normally for {args.seconds:.0f} seconds.\n")

    frames = []

    def cb(indata, n, t, status):
        if status:
            print(f"  status: {status}")
        frames.append(indata.copy())

    with sd.InputStream(device=device, channels=channels, samplerate=rate,
                        dtype="float32", callback=cb):
        start = time.time()
        while time.time() - start < args.seconds:
            time.sleep(0.2)
            if frames:
                peak = max(db(f) for f in frames[-4:])
                bar = "#" * int(np.clip((peak + 70) / 70 * 40, 0, 40))
                print(f"\r  {peak:6.1f} dBFS  [{bar:<40}]", end="", flush=True)
    print("\n")

    if not frames:
        print("  nothing captured")
        return 1

    audio = np.concatenate(frames, axis=0)
    print("  " + "=" * 52)
    for c in range(audio.shape[1]):
        ch = audio[:, c]
        loud = ch[np.abs(ch) > 10 ** (-60 / 20)]
        share = len(loud) / len(ch)
        print(f"  channel {c}   overall {db(ch):6.1f} dBFS   peak "
              f"{20*np.log10(np.abs(ch).max()+1e-12):6.1f} dBFS   "
              f"{share:5.1%} above -60")

    mono = audio.mean(axis=1) if audio.shape[1] > 1 else audio[:, 0]
    print(f"\n  after mixing to mono: {db(mono):.1f} dBFS")
    if audio.shape[1] > 1:
        best = max(db(audio[:, c]) for c in range(audio.shape[1]))
        lost = best - db(mono)
        if lost > 3:
            print(f"  loudest single channel is {lost:.1f} dB above the mix, "
                  f"so\n  averaging is costing level. One channel is probably "
                  f"dead.")
    print("  " + "=" * 52)

    peak_db = 20 * np.log10(np.abs(mono).max() + 1e-12)
    print(f"\n  peak {peak_db:.1f} dBFS")
    if peak_db < -30:
        print("  Very low. Raise the capture volume: alsamixer (F4) on Linux,")
        print("  or Sound settings on Windows.")
    elif peak_db > -3:
        print("  Close to clipping. Lower the capture volume.")
    else:
        print("  Reasonable. Speech peaking between -20 and -6 is healthy.")
    return 0


if __name__ == "__main__":
    sys.exit(main())