#!/usr/bin/env python3
"""Render token-consumption visuals with the abyssal-navy art style.

Tracks two token universes every day:
  * Hermes Agent via NVIDIA NIM (from ~/.hermes/state.db + archives)
  * Claude Code CLI (from ~/.claude/projects/*.jsonl)

Sources are scanned so the daily run always reflects real, up-to-date data.
"""

import glob
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from theme import W, defs, canvas, close_svg, stat_card, FONT, MONO, NVIDIA, ANTHROPIC

TOKEN_FILE = Path(__file__).parent.parent / "token_lifetime.json"
CLAUDE_DIR = Path.home() / ".claude" / "projects"


def load_hermes_tokens():
    """Read the lifetime NIM total from token_lifetime.json."""
    if not TOKEN_FILE.exists():
        return {"lifetime_total": 0, "sessions_count": 0, "last_update": "", "breakdown": {}}
    try:
        return json.loads(TOKEN_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return {"lifetime_total": 0, "sessions_count": 0, "last_update": "", "breakdown": {}}


def claude_tokens():
    """Aggregate Claude Code CLI token usage across all project JSONL files."""
    per_model = defaultdict(lambda: {"in": 0, "out": 0, "cache_r": 0, "cache_w": 0})
    sessions = set()
    cost = 0.0
    files = 0
    if not CLAUDE_DIR.exists():
        return per_model, sessions, cost, files
    for path in CLAUDE_DIR.rglob("*.jsonl"):
        files += 1
        try:
            lines = path.read_text(errors="replace").splitlines()
        except OSError:
            continue
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            sid = record.get("sessionId")
            if sid:
                sessions.add(sid)
            mu = record.get("modelUsage") or {}
            for model, usage in mu.items():
                if not isinstance(usage, dict):
                    continue
                entry = per_model[model]
                entry["in"] += int(usage.get("inputTokens") or 0)
                entry["out"] += int(usage.get("outputTokens") or 0)
                entry["cache_r"] += int(usage.get("cacheReadInputTokens") or 0)
                entry["cache_w"] += int(usage.get("cacheCreationInputTokens") or 0)
            if record.get("totalCostUSD"):
                try:
                    cost += float(record["totalCostUSD"])
                except (TypeError, ValueError):
                    pass
    return per_model, sessions, cost, files


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


def render(hermes, claude_map, sessions, cost, files):
    n_total = hermes.get("lifetime_total", 0)
    n_sessions = hermes.get("sessions_count", 0)
    c_total = sum(sum(d.values()) for d in claude_map.values())

    grand = n_total + c_total
    hermes_pct = 100.0 * n_total / grand if grand else 0
    claude_pct = 100.0 * c_total / grand if grand else 0

    parts = []
    parts.append(canvas(W, 420, "t", "Lifetime Token Consumption",
                        "Hermes Agent (NVIDIA NIM) vs Claude Code CLI — daily tracked",
                        f"Updated {datetime.now().strftime('%b %d, %Y')}"))
    parts.append(defs("t"))

    # Big headline cards
    parts.append(stat_card(28, 100, 452, 130, "Hermes (NVIDIA NIM)",
                           human(n_total), NVIDIA,
                           sublabel=f"{n_sessions:,} sessions • {hermes_pct:.1f}% of all tokens",
                           prefix="t", value_size=30))
    parts.append(stat_card(500, 100, 432, 130, "Claude Code CLI",
                           human(c_total), ANTHROPIC,
                           sublabel=f"{len(sessions)} sessions • ${cost:,.2f} cost",
                           prefix="t", value_size=30))

    # Grand total
    parts.append(stat_card(28, 252, 904, 100, "Combined Token Total",
                           human(grand), "#22d3ee",
                           sublabel=f"Updated daily by cron • {hermes_pct:.1f}% NIM / {claude_pct:.1f}% Claude",
                           prefix="t", value_size=28))

    # Claude model breakdown chips
    cx, cy = 28, 372
    sorted_models = sorted(claude_map.items(), key=lambda kv: -sum(kv[1].values()))
    x = cx
    for model, d in sorted_models[:6]:
        m_total = sum(d.values())
        text = f"{model.split('/')[-1]} {human(m_total)}"
        w = len(text) * 7.4 + 16
        parts.append(
            f'  <rect x="{x}" y="{cy}" width="{w:.0f}" height="30" rx="15" '
            f'fill="#142040" stroke="{ANTHROPIC}" stroke-opacity="0.5" stroke-width="1"/>'
        )
        parts.append(
            f'  <text x="{x + w / 2:.0f}" y="{cy + 19.5}" fill="#e9eefb" font-size="10.5" '
            f'font-weight="600" text-anchor="middle" font-family="{FONT}">{text}</text>'
        )
        x += w + 10

    parts.append(close_svg([]))
    return "\n".join(parts)


def main():
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
    out.mkdir(parents=True, exist_ok=True)
    hermes = load_hermes_tokens()
    claude_map, sessions, cost, files = claude_tokens()
    svg = render(hermes, claude_map, sessions, cost, files)
    svg_path = out / "token-stats.svg"
    svg_path.write_text(svg)
    print(f"Token chart → {svg_path} ({len(svg)} bytes) "
          f"NIM={human(hermes.get('lifetime_total',0))} Claude={human(sum(sum(d.values()) for d in claude_map.values()))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
