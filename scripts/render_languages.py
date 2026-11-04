#!/usr/bin/env python3
"""Render language-breakdown cards — clean and readable."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from theme import W, canvas, close_svg, FONT, MONO

STATS_JSON = Path(__file__).parent.parent / "bot-stats.json"

LANG_COLORS = {
    "Python": "#3572A5",
    "TypeScript": "#3178c6",
    "JavaScript": "#f1e05a",
    "Rust": "#dea584",
    "C": "#555555",
    "C++": "#f34b7d",
    "Go": "#00ADD8",
    "Java": "#b07219",
    "HTML": "#e34c26",
    "CSS": "#563d7c",
    "Shell": "#89e051",
    "Lua": "#000080",
    "Luau": "#000080",
}


def render(stats):
    langs = stats.get("languages", [])
    parts = []
    parts.append(canvas(W, 300, "l", "Languages & Stack",
                        "Repositories by primary language • live from the GitHub API",
                        f"Updated {stats.get('generated_at','')[:10]}"))

    # Summary line
    parts.append(
        f'  <text x="32" y="72" fill="#eef2fb" font-size="15" font-weight="800" '
        f'font-family="{FONT}">{stats["total_repos"]} repositories</text>'
    )
    parts.append(
        f'  <text x="32" y="90" fill="#93a3c1" font-size="11" font-family="{MONO}">'
        f'{stats["public_repos"]} public · {stats["private_repos"]} private · '
        f'{stats["original_repos"]} original · {stats["forked_repos"]} forks · '
        f'{stats["stars"]} stars</text>'
    )

    # Language cards in a row
    if langs:
        y = 120
        gap = 16
        card_w = (W - 64 - gap * (len(langs) - 1)) / len(langs)
        card_w = max(card_w, 100)
        x = 32
        for lang in langs:
            name = lang["name"]
            count = lang["count"]
            color = lang.get("color") or LANG_COLORS.get(name, "#8b949e")
            pct = count / stats["total_repos"] * 100 if stats["total_repos"] else 0
            parts.append(
                f'  <rect x="{x}" y="{y}" width="{card_w}" height="100" rx="12" '
                f'fill="#111930" stroke="#273254" stroke-width="1"/>'
            )
            parts.append(
                f'  <circle cx="{x + 16}" cy="{y + 24}" r="8" fill="{color}"/>'
            )
            parts.append(
                f'  <text x="{x + 30}" y="{y + 27}" fill="#eef2fb" font-size="12.5" '
                f'font-weight="700" font-family="{FONT}">{name}</text>'
            )
            parts.append(
                f'  <text x="{x + card_w / 2}" y="{y + 56}" fill="#93a3c1" font-size="10" '
                f'text-anchor="middle" font-family="{MONO}">{count} repo{"s" if count != 1 else ""}</text>'
            )
            parts.append(
                f'  <text x="{x + card_w / 2}" y="{y + 78}" fill="#eef2fb" font-size="13" font-weight="800" '
                f'text-anchor="middle" font-family="{FONT}">{pct:.0f}%</text>'
            )
            x += card_w + gap

    parts.append(close_svg([]))
    return "\n".join(parts)


def main():
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
    out.mkdir(parents=True, exist_ok=True)
    if not STATS_JSON.exists():
        print("ERROR: bot-stats.json not found — run github_stats.py first", file=sys.stderr)
        return 1
    stats = json.loads(STATS_JSON.read_text())
    svg = render(stats)
    svg_path = out / "languages.svg"
    svg_path.write_text(svg)
    print(f"Languages chart → {svg_path} ({len(svg)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
