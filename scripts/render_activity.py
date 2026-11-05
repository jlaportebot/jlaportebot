#!/usr/bin/env python3
"""Render the GitHub activity chart — clean, readable, cumulative lines over time.

Shows five cumulative series:
- Repos created (total)
- PRs opened
- PRs currently open
- PRs merged
- PRs closed (not merged)

All series are monotonic cumulative totals drawn from gh-activity-chart.json,
which is produced by the gh_activity_chart.py data generator.
"""
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from theme import W, defs, canvas, close_svg, FONT, MONO

CHART_JSON = Path(__file__).parent.parent / "gh-activity-chart.json"

# Canvas height gives the plot room to breathe so lines aren't crushed.
CANVAS_H = 380


def load_json():
    if not CHART_JSON.exists():
        return None
    return json.loads(CHART_JSON.read_text())


def render(data):
    Wv, Hv = W, CANVAS_H
    margin = {"top": 64, "right": 120, "bottom": 56, "left": 52}
    plotW = Wv - margin["left"] - margin["right"]
    plotH = Hv - margin["top"] - margin["bottom"]

    repos = [d["repos_total"] for d in data]
    opened = [d["prs_opened_total"] for d in data]
    open_ = [d["prs_open_total"] for d in data]
    merged = [d["prs_merged_total"] for d in data]
    closed = [d["prs_closed_total"] for d in data]
    all_vals = repos + opened + open_ + merged + closed
    max_y = max(all_vals) if all_vals else 10
    # Headroom so the top line never touches the ceiling.
    max_y = max_y * 1.15 + 8

    n = max(len(data) - 1, 1)

    def sx(i):
        return margin["left"] + (i / n) * plotW

    def sy(v):
        return margin["top"] + plotH - (v / max_y) * plotH

    def path(vals):
        pts = [f"{sx(i):.1f},{sy(v):.1f}" for i, v in enumerate(vals)]
        return "M " + " L ".join(pts)

    def area(vals, base=0):
        pts = [f"{sx(i):.1f},{sy(v):.1f}" for i, v in enumerate(vals)]
        last = len(vals) - 1
        pts.append(f"{sx(last):.1f},{sy(base):.1f}")
        pts.append(f"{sx(0):.1f},{sy(base):.1f}")
        return "M " + " L ".join(pts) + " Z"

    parts = []
    parts.append(canvas(Wv, Hv, "a", "GitHub Activity",
                        "Cumulative lifetime activity • repos · PRs opened · merged · closed · open",
                        f"Updated {datetime.now().strftime('%b %d, %Y')}"))
    parts.append(defs("a"))

    series = [
        (opened, "#58a6ff", "Opened"),
        (repos, "#f78166", "Repos"),
        (open_, "#34d399", "Open PRs"),
        (merged, "#a78bfa", "Merged"),
        (closed, "#f472b6", "Closed"),
    ]

    # Faint filled areas under the two largest series.
    for vals, color, _ in series[:2]:
        parts.append(f'  <path d="{area(vals)}" fill="{color}" fill-opacity="0.08"/>')

    # Lines + end dots + end labels.
    for vals, color, label in series:
        parts.append(
            f'  <path d="{path(vals)}" fill="none" stroke="{color}" '
            f'stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>'
        )
        x, y = sx(len(vals) - 1), sy(vals[-1])
        parts.append(f'  <circle cx="{x:.1f}" cy="{y:.1f}" r="3.6" fill="{color}"/>')
        # Stagger end labels vertically so they don't collide.
        label_y = y + 6
        parts.append(
            f'  <text x="{x + 10:.1f}" y="{label_y:.1f}" fill="{color}" '
            f'font-size="11" font-weight="800" font-family="{FONT}">{vals[-1]}</text>'
        )
        parts.append(
            f'  <text x="{x + 10:.1f}" y="{label_y + 12:.1f}" fill="{color}" '
            f'font-size="9" font-weight="600" font-family="{MONO}" opacity="0.7">{label}</text>'
        )

    # Y grid.
    y_step = 10 if max_y > 30 else 5
    for t in range(0, int(max_y) + 1, int(y_step)):
        y = sy(t)
        parts.append(
            f'  <line x1="{margin["left"]:.1f}" y1="{y:.1f}" '
            f'x2="{Wv - margin["right"]:.1f}" y2="{y:.1f}" stroke="#273254" stroke-width="1"/>'
        )
        parts.append(
            f'  <text x="{margin["left"] - 10:.1f}" y="{y + 4:.1f}" fill="#6270a1" '
            f'font-size="10" text-anchor="end" font-family="{MONO}">{t}</text>'
        )

    # X labels.
    step = max(1, len(data) // 8)
    for i in range(0, len(data), step):
        x = sx(i)
        dt = datetime.strptime(data[i]["date"], "%Y-%m-%d")
        label = dt.strftime("%b %d")
        parts.append(
            f'  <text x="{x:.1f}" y="{Hv - margin["bottom"] + 18}" fill="#6270a1" font-size="10" '
            f'text-anchor="middle" font-family="{MONO}">{label}</text>'
        )

    parts.append(close_svg([]))
    return "\n".join(parts)


def main():
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
    out.mkdir(parents=True, exist_ok=True)
    data_raw = load_json()
    if not data_raw:
        print("ERROR: gh-activity-chart.json not found", file=sys.stderr)
        return 1
    data = data_raw.get("daily", [])
    if not data:
        print("ERROR: no daily data", file=sys.stderr)
        return 1
    svg = render(data)
    svg_path = out / "gh-activity-chart.svg"
    svg_path.write_text(svg)
    print(f"Activity chart → {svg_path} ({len(svg)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
