r"""Interruption accuracy and backchannel false-stop rate (plan.md X8).

Run from the repository root:
    backend\.venv\Scripts\python eval\interruptions.py      (Windows)
    backend/.venv/bin/python eval/interruptions.py          (macOS, Linux)
"""

import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import harness  # noqa: E402
import scenarios  # noqa: E402


def main() -> int:
    cases = scenarios.build()
    results = [(case, harness.run(case)) for case in cases]

    interrupts = [(c, r) for c, r in results if c.kind == "interrupt"]
    backchannels = [(c, r) for c, r in results if c.kind == "backchannel"]
    blips = [(c, r) for c, r in results if c.kind == "blip"]

    stopped = sum(r.interrupted for _, r in interrupts)
    false_stops = sum(r.interrupted for _, r in backchannels)
    blip_stops = sum(r.interrupted for _, r in blips)
    errors = [r.trim_error_words for _, r in interrupts if r.interrupted]

    print(f"scenarios: {len(cases)} ({len(interrupts)} interruptions, {len(backchannels)} backchannels, {len(blips)} blips)")
    print(f"interruption accuracy:        {stopped}/{len(interrupts)} stopped TalkBack ({100 * stopped / len(interrupts):.0f}%)")
    print(f"backchannel false-stop rate:  {false_stops}/{len(backchannels)} ({100 * false_stops / len(backchannels):.0f}%)")
    print(f"short-noise false-stop rate:  {blip_stops}/{len(blips)} ({100 * blip_stops / len(blips):.0f}%)")
    if errors:
        print(f"trim error (words):           mean {statistics.mean(errors):.2f}, max {max(errors)}")
    for case, result in results:
        right = result.interrupted == (case.kind == "interrupt")
        if not right:
            print(f"  WRONG: {case.name}: text={case.text!r} speech={case.speech_ms} ms -> stopped={result.interrupted}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
