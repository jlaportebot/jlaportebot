#!/usr/bin/env python3
"""Regenerate README.md — minimal, readable.

Title only, then the three dashboard sections (charts).
"""

import json
import sys
from pathlib import Path

REPO_DIR = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
BOT_STATS = REPO_DIR / "bot-stats.json"
TOKEN_FILE = REPO_DIR / "token_lifetime.json"
README = REPO_DIR / "README.md"


def load(path, default=None):
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return default


def human(n):
    if n is None:
        return "0"
    n = float(n)
    for limit, suffix in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")):
        if abs(n) >= limit:
            val = n / limit
            text = f"{val:.2f}".rstrip("0").rstrip(".")
            return f"{text}{suffix}"
    return str(int(n))


def main():
    token = load(TOKEN_FILE, {}) or {}
    stats = load(BOT_STATS, {}) or {}

    n_total = token.get("lifetime_total", 0)
    claude_total = token.get("claude_total", 0)

    grand = n_total + claude_total

    lines = []
    lines.append("# jlaportebot")
    lines.append("")

    lines.append('<img src="./gh-activity-chart.svg" alt="GitHub Activity Chart" width="960"/>')
    lines.append("")
    lines.append('<img src="./token-stats.svg" alt="Lifetime Token Consumption" width="960"/>')
    lines.append("")
    lines.append('<img src="./loc-stats.svg" alt="Lifetime Lines of Code" width="960"/>')
    lines.append("")

    README.write_text("\n".join(lines))
    print(f"README → {README} (NIM={human(n_total)} Claude={human(claude_total)} Total={human(grand)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
