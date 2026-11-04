#!/usr/bin/env python3
"""Regenerate README.md — minimal, readable.

Title, a prominent NIM / Claude / Total token line, then the charts.
All the extra "what this tracks / how it's built" text is removed.
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
    n_sessions = token.get("sessions_count", 0)
    updated = token.get("last_update", "")[:10]

    # Claude tokens from Claude Code CLI (best-effort)
    claude_total = 0
    session_ids = set()
    cost = 0.0
    try:
        claude_dir = Path.home() / ".claude" / "projects"
        for path in claude_dir.rglob("*.jsonl"):
            try:
                lines = path.read_text(errors="replace").splitlines()
            except OSError:
                continue
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if rec.get("sessionId"):
                    session_ids.add(rec["sessionId"])
                mu = rec.get("modelUsage") or {}
                for usage in mu.values():
                    if isinstance(usage, dict):
                        claude_total += int(usage.get("inputTokens") or 0)
                        claude_total += int(usage.get("outputTokens") or 0)
                        claude_total += int(usage.get("cacheReadInputTokens") or 0)
                        claude_total += int(usage.get("cacheCreationInputTokens") or 0)
                if rec.get("totalCostUSD"):
                    try:
                        cost += float(rec["totalCostUSD"])
                    except (TypeError, ValueError):
                        pass
    except Exception:
        pass

    grand = n_total + claude_total

    lines = []
    lines.append("# jlaportebot")
    lines.append("")
    lines.append("Autonomous agent dashboard — live telemetry updated daily by cron.")
    lines.append("")
    lines.append(
        f"**🤖 Tokens:** "
        f"**NVIDIA NIM {human(n_total)}**  ·  "
        f"**Claude {human(claude_total)}**  ·  "
        f"**Total {human(grand)}**"
    )
    lines.append("")
    lines.append(f"_NIM: {n_sessions:,} sessions • Claude: {len(session_ids)} sessions • ${cost:,.2f} cost • Updated {updated}_")
    lines.append("")
    lines.append('<img src="./gh-activity-chart.svg" alt="GitHub Activity Chart" width="960"/>')
    lines.append("")
    lines.append('<img src="./token-stats.svg" alt="Lifetime Token Consumption" width="960"/>')
    lines.append("")
    lines.append('<img src="./loc-stats.svg" alt="Lifetime Lines of Code" width="960"/>')
    lines.append("")
    lines.append('<img src="./languages.svg" alt="Languages & Stack" width="960"/>')
    lines.append("")

    README.write_text("\n".join(lines))
    print(f"README → {README} (NIM={human(n_total)} Claude={human(claude_total)} Total={human(grand)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
