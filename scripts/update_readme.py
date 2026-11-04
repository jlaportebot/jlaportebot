#!/usr/bin/env python3
"""Regenerate README.md from live stats files.

Reads:
  * bot-stats.json        (github_stats.py)
  * token_lifetime.json   (token_tracker.py --update)

Writes README.md to the repo root. Idempotent.
"""

import json
import os
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
    stats = load(BOT_STATS, {}) or {}
    token = load(TOKEN_FILE, {}) or {}

    n_total = token.get("lifetime_total", 0)
    n_sessions = token.get("sessions_count", 0)
    updated = token.get("last_update", "")[:10]

    # Claude tokens from Claude Code CLI (best-effort)
    claude_total = 0
    try:
        from pathlib import Path as P
        import glob
        claude_dir = P.home() / ".claude" / "projects"
        for path in claude_dir.rglob("*.jsonl"):
            for line in path.read_text(errors="replace").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                mu = rec.get("modelUsage") or {}
                for usage in mu.values():
                    if isinstance(usage, dict):
                        claude_total += int(usage.get("inputTokens") or 0)
                        claude_total += int(usage.get("outputTokens") or 0)
                        claude_total += int(usage.get("cacheReadInputTokens") or 0)
                        claude_total += int(usage.get("cacheCreationInputTokens") or 0)
    except Exception:
        pass

    lines = []
    lines.append("# jlaportebot")
    lines.append("")
    lines.append("**Autonomous agent dashboard.** Live telemetry for the `jlaportebot` GitHub presence — activity, code volume, token consumption, and language stack — updated daily by a bulletproof cron job.")
    lines.append("")
    lines.append('<img src="./gh-activity-chart.svg" alt="GitHub Activity Chart" width="960"/>')
    lines.append("")
    lines.append('<img src="./token-stats.svg" alt="Lifetime Token Consumption" width="960"/>')
    lines.append("")
    lines.append('<img src="./loc-stats.svg" alt="Lifetime Lines of Code" width="960"/>')
    lines.append("")
    lines.append('<img src="./languages.svg" alt="Languages & Stack" width="960"/>')
    lines.append("")
    lines.append("## What this tracks")
    lines.append("")
    lines.append("| Chart | Source | Updated |")
    lines.append("|-------|--------|---------|")
    lines.append("| **GitHub Activity** | `gh` API — PRs opened/merged/closed, repos created, open PRs | Daily via cron |")
    lines.append("| **Token Consumption** | Hermes state.db + archive (NVIDIA NIM) + Claude Code CLI projects | Daily via cron |")
    lines.append("| **Lines of Code** | GitHub stats/contributors API (owned) + PR diff API (external) | Daily via cron |")
    lines.append("| **Languages & Stack** | GitHub user/repos API | Daily via cron |")
    lines.append("")
    lines.append("## Functional stats (live)")
    lines.append("")
    lines.append(f"- **🟠 Repos:** {stats.get('total_repos','?')} total ({stats.get('public_repos','?')} public · {stats.get('private_repos','?')} private · {stats.get('original_repos','?')} original · {stats.get('forked_repos','?')} forks)")
    lines.append(f"- **⭐ Stars:** {stats.get('stars','?')} received · **👀 Watchers:** {stats.get('watchers','?')} · **🐛 Open issues:** {stats.get('open_issues','?')}")
    lines.append(f"- **🔀 PRs authored:** {stats.get('prs_authored','?')} lifetime · **📝 Issues authored:** {stats.get('issues_authored','?')}")
    langs = stats.get("languages", [])
    if langs:
        lang_str = " · ".join(f"{l['name']} ({l['count']})" for l in langs[:8])
        lines.append(f"- **🌐 Languages:** {lang_str}")
    lines.append(f"- **🤖 Token split:** NVIDIA NIM (Hermes Agent) {human(n_total)} vs Claude Code CLI {human(claude_total)} — tracked daily, never resets")
    lines.append(f"- **📅 Account:** created May 2026 · **📍 Raspberry Pi 5** · **🔗** https://github.com/jlaportebot")
    lines.append("")
    lines.append("## How it's built")
    lines.append("")
    lines.append("- **Zero cost** — GitHub API + local Hermes state, no paid services")
    lines.append("- **Deterministic** — cached per-repo LOC, monotonic counters, deduped token sources")
    lines.append("- **Art style** — abyssal-navy canvas, aurora bloom gradients, glass cards, neon series lines")
    lines.append("- **Bulletproof cron** — runs every day at 5:30 AM EST, retries on failure, verifies the push landed on remote before reporting success")
    lines.append("")
    lines.append(f"---\n")
    lines.append(f"_Generated by the jlaportebot stats pipeline. Regenerated daily — do not edit the SVGs by hand. Last data refresh: {updated}._")
    lines.append("")

    README.write_text("\n".join(lines))
    print(f"README → {README} (tokens={human(n_total)}, sessions={n_sessions}, claude={human(claude_total)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
