"""How long TalkBack keeps talking after the user starts (plan.md X8).

This is the turn-taking part of the delay only (speech detection plus the
250 ms minimum and the recognizer's first words). The browser also needs up
to 150 ms to flush playback (design.md 3.4). End-to-end numbers with the real
speech engine need a live run.
"""

import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import harness  # noqa: E402
import scenarios  # noqa: E402


def percentile(values: list[int], p: float) -> int:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(p * len(ordered)))]


def main() -> int:
    times = [
        r.stop_after_ms
        for c in scenarios.build()
        if c.kind == "interrupt" and (r := harness.run(c)).stop_after_ms is not None
    ]
    print(f"interruptions measured: {len(times)}")
    print(f"time from speech start to stop: median {statistics.median(times):.0f} ms, p95 {percentile(times, 0.95)} ms")
    print(f"(recognizer shows words after {scenarios.ASR_DELAY_MS} ms in these scenarios)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
