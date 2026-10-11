"""Run the end-to-end scenarios against a TalkBack server (plan P9).

    backend/.venv/Scripts/python eval/audio_fixtures.py      # once
    backend/.venv/Scripts/python eval/run_e2e.py --target http://127.0.0.1:8000 --runs 5
    backend/.venv/Scripts/python eval/run_e2e.py --target https://talkback-voice.onrender.com --code XXXX

Writes eval/results/<date>-<HHMM>-<commit>-<target>.json and .md. Then
eval/report.py puts the latest numbers in the README.
"""

import argparse
import asyncio
import json
import statistics
import subprocess
import sys
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from e2e_scenarios import SCENARIOS, run  # noqa: E402

RESULTS = ROOT / "results"
LATENCY = {"question": "Spoken question → first audio", "typed": "Typed question → first audio",
           "barge_in": "\"Wait, stop\" → audio stops"}
RECOVERY = {"barge_in": "Stops when interrupted", "backchannel": "Keeps talking through \"uh-huh\"",
            "correction": "Correction during a confirmation", "cancel_tool": "\"Never mind\" during a tool call"}


def percentile(values: list[float], p: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(p * (len(ordered) - 1)))]


def summarize(results: list[dict]) -> dict:
    out: dict = {"latency_ms": {}, "recovery": {}, "outdated_actions": 0, "runs": {}}
    for name in SCENARIOS:
        mine = [r for r in results if r["scenario"] == name]
        if not mine:
            continue
        ok = [r for r in mine if r["ok"]]
        out["runs"][name] = {"ok": len(ok), "total": len(mine)}
        times = [r["ms"] for r in ok if r["ms"] is not None]
        if name in LATENCY and times:
            out["latency_ms"][name] = {"p50": round(statistics.median(times)), "p95": round(percentile(times, 0.95)),
                                       "n": len(times)}
        if name in RECOVERY:
            out["recovery"][name] = round(len(ok) / len(mine), 3)
        out["outdated_actions"] += sum(1 for r in mine if r["outdated_action"])
    return out


def markdown(meta: dict, summary: dict, results: list[dict]) -> str:
    lines = [f"# End-to-end run: {meta['target']}", "",
             f"{meta['date']} · commit `{meta['commit']}` · {meta['runs']} run(s) per scenario", "",
             "| Latency (warm) | p50 | p95 | runs |", "|---|---|---|---|"]
    for name, label in LATENCY.items():
        if name in summary["latency_ms"]:
            m = summary["latency_ms"][name]
            lines.append(f"| {label} | {m['p50']} ms | {m['p95']} ms | {m['n']} |")
    lines += ["", "| Recovery | passed |", "|---|---|"]
    for name, label in RECOVERY.items():
        if name in summary["runs"]:
            r = summary["runs"][name]
            lines.append(f"| {label} | {r['ok']} of {r['total']} |")
    lines += ["", f"Outdated actions (a corrected change that happened anyway): **{summary['outdated_actions']}**", "",
              "## Every run", "", "| Scenario | OK | ms | Note |", "|---|---|---|---|"]
    for r in results:
        ms = "" if r["ms"] is None else f"{r['ms']:.0f}"
        lines.append(f"| {r['scenario']} | {'yes' if r['ok'] else 'no'} | {ms} | {r['note']} |")
    return "\n".join(lines) + "\n"


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", required=True)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--code", default="", help="access code, if the server needs one")
    parser.add_argument("--only", nargs="*", choices=list(SCENARIOS), help="some scenarios only")
    args = parser.parse_args()
    names = args.only or list(SCENARIOS)
    results = []
    for round_ in range(args.runs):
        for name in names:
            started = time.monotonic()
            result = await run(name, args.target.rstrip("/"), args.code)
            results.append(asdict(result))
            ms = "" if result.ms is None else f" {result.ms:.0f} ms"
            print(f"[{round_ + 1}/{args.runs}] {name}: {'ok' if result.ok else 'FAILED'}{ms} {result.note}"
                  f" ({time.monotonic() - started:.0f} s)", flush=True)
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                            cwd=ROOT).stdout.strip() or "unknown"
    host = urlsplit(args.target).hostname or "target"
    target = "local" if host in ("127.0.0.1", "localhost") else host.split(".")[0]
    meta = {"target": target, "url": args.target, "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "commit": commit, "runs": args.runs}
    summary = summarize(results)
    RESULTS.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%H%M")  # two runs of one commit keep both files
    stem = RESULTS / f"{meta['date']}-{stamp}-{commit}-{target}"
    stem.with_suffix(".json").write_text(json.dumps({"meta": meta, "summary": summary, "results": results}, indent=2),
                                         encoding="utf-8")
    stem.with_suffix(".md").write_text(markdown(meta, summary, results), encoding="utf-8")
    print(f"\nwrote {stem.with_suffix('.md').relative_to(ROOT.parent)}")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
