"""Put the latest end-to-end numbers in the README (plan P9).

    backend/.venv/Scripts/python eval/report.py

Reads the newest eval/results/*.json for each target (local, the hosted
demo), writes eval/results/latency.svg, and replaces the README text between
<!-- eval:start --> and <!-- eval:end -->.
"""

import json
import sys
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from run_e2e import LATENCY, RECOVERY  # noqa: E402

RESULTS = ROOT / "results"
README = ROOT.parent / "README.md"
START, END = "<!-- eval:start -->", "<!-- eval:end -->"
NAMES = {"local": "Local server", "talkback-voice": "Hosted demo (Render free tier)"}


def latest() -> dict[str, dict]:
    newest: dict[str, dict] = {}
    for path in sorted(RESULTS.glob("*.json")):  # names start with the date
        data = json.loads(path.read_text(encoding="utf-8"))
        data["file"] = path.name
        newest[data["meta"]["target"]] = data
    return newest


def chart(runs: dict[str, dict]) -> str:
    """Horizontal bars: p50 solid, p95 as a lighter extension. Plain SVG, no fonts to load."""
    rows = [(f"{NAMES.get(t, t)}: {label}", d["summary"]["latency_ms"][name])
            for t, d in runs.items() for name, label in LATENCY.items() if name in d["summary"]["latency_ms"]]
    if not rows:
        return ""
    top = max(m["p95"] for _, m in rows)
    scale = 420 / max(top, 1)
    height = 24 + 34 * len(rows) + 28
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="760" height="{height}" viewBox="0 0 760 {height}" '
             'font-family="system-ui, sans-serif" font-size="12">',
             '<rect width="100%" height="100%" fill="#ffffff"/>',
             '<text x="8" y="16" fill="#333">Warm latency, milliseconds (bar: p50, light extension: p95)</text>']
    for i, (label, m) in enumerate(rows):
        y = 28 + i * 34
        parts += [
            f'<text x="8" y="{y + 15}" fill="#333">{escape(label)}</text>',
            f'<rect x="300" y="{y + 4}" width="{m["p95"] * scale:.1f}" height="16" fill="#9ecae1"/>',
            f'<rect x="300" y="{y + 4}" width="{m["p50"] * scale:.1f}" height="16" fill="#2171b5"/>',
            f'<text x="{300 + m["p95"] * scale + 6:.1f}" y="{y + 16}" fill="#333">{m["p50"]} / {m["p95"]}</text>',
        ]
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def section(runs: dict[str, dict]) -> str:
    lines = [START, ""]
    if not runs:
        return "\n".join([START, "", "No end-to-end runs yet.", "", END])
    targets = list(runs)
    header = "| | " + " | ".join(NAMES.get(t, t) for t in targets) + " |"
    rule = "|---|" + "---|" * len(targets)
    lines += ["| Latency, warm (p50 / p95) | " + " | ".join(NAMES.get(t, t) for t in targets) + " |", rule]
    for name, label in LATENCY.items():
        cells = []
        for t in targets:
            m = runs[t]["summary"]["latency_ms"].get(name)
            cells.append(f"{m['p50']} / {m['p95']} ms" if m else "—")
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
    lines += ["", header.replace("| |", "| Recovery |", 1), rule]
    for name, label in RECOVERY.items():
        cells = []
        for t in targets:
            r = runs[t]["summary"]["runs"].get(name)
            cells.append(f"{r['ok']} of {r['total']}" if r else "—")
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
    lines.append("| Outdated actions (a corrected change that happened anyway) | "
                 + " | ".join(str(runs[t]["summary"]["outdated_actions"]) for t in targets) + " |")
    lines += ["", "Runs: " + "; ".join(
        f"{NAMES.get(t, t)} {d['meta']['date']}, commit `{d['meta']['commit']}`, {d['meta']['runs']} per scenario "
        f"([details](eval/results/{d['file'].replace('.json', '.md')}))" for t, d in runs.items()) + "."]
    if (RESULTS / "latency.svg").exists():
        lines += ["", "![Warm latency chart](eval/results/latency.svg)"]
    lines += ["", END]
    return "\n".join(lines)


def main() -> int:
    runs = latest()
    svg = chart(runs)
    if svg:
        (RESULTS / "latency.svg").write_text(svg, encoding="utf-8")
    text = README.read_text(encoding="utf-8")
    if START not in text or END not in text:
        print("README has no eval markers")
        return 1
    before, rest = text.split(START, 1)
    _, after = rest.split(END, 1)
    README.write_text(before + section(runs) + after, encoding="utf-8")
    print(f"README updated from {', '.join(d['file'] for d in runs.values()) or 'no runs'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
