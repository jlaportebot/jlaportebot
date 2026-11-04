#!/usr/bin/env python3
"""Render token consumption: NVIDIA NIM vs Claude Code CLI vs Combined Total.

Three big clean cards — easy to read at a glance on the profile README.
"""

import glob
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from theme import W, defs, canvas, close_svg, stat_card, FONT, MONO, NVIDIA, ANTHROPIC, TOTAL

TOKEN_FILE = Path(__file__).parent.parent / "token_lifetime.json"
CLAUDE_DIR = Path.home() / ".claude" / "projects"


def load_hermes_tokens():
    """Read the lifetime NIM total from token_lifetime.json."""
    if not TOKEN_FILE.exists():
        return {"lifetime_total": 0, "sessions_count": 0, "last_update": ""}
    try:
        return json.loads(TOKEN_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return {"lifetime_total": 0, "sessions_count": 0, "last_update": ""}


def claude_tokens():
    """Aggregate Claude Code CLI token usage across all project JSONL files."""
    per_model = defaultdict(lambda: {"in": 0, "out": 0, "cache_r": 0, "cache_w": 0})
    session_ids = set()
    cost = 0.0
    if not CLAUDE_DIR.exists():
        return per_model, session_ids, cost
    for path in CLAUDE_DIR.rglob("*.jsonl"):
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
                session_ids.add(sid)
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
    return per_model, session_ids, cost


def render(nim_total, nim_sessions, nim_updated, claude_total, sessions, cost):
    grand = nim_total + claude_total
    nim_pct = 100.0 * nim_total / grand if grand else 0
    claude_pct = 100.0 * claude_total / grand if grand else 0

    parts = []
    parts.append(canvas(W, 340, "t", "Lifetime Token Consumption",
                        "Hermes Agent (NVIDIA NIM) · Claude Code CLI · Combined",
                        f"Updated {nim_updated[:10] if nim_updated else ''}"))
    parts.append(defs("t"))

    cw = (W - 64 - 40) / 3  # card width for 3 across

    # Card 1: NVIDIA NIM
    parts.append(stat_card(32, 110, cw, 160, "NVIDIA NIM (Hermes Agent)",
                           human(nim_total), NVIDIA,
                           value_size=32,
                           sublabel=f"{nim_sessions:,} sessions  •  {nim_pct:.1f}% of total"))

    # Card 2: Claude Code CLI
    cx = 32 + cw + 20
    parts.append(stat_card(cx, 110, cw, 160, "Claude Code CLI",
                           human(claude_total), ANTHROPIC,
                           value_size=32,
                           sublabel=f"{len(sessions)} sessions  •  ${cost:,.2f} cost  •  {claude_pct:.1f}% of total"))

    # Card 3: Total
    tx = cx + cw + 20
    parts.append(stat_card(tx, 110, cw, 160, "Combined Total",
                           human(grand), TOTAL,
                           value_size=34,
                           sublabel=f"NIM {human(nim_total)} + Claude {human(claude_total)}  •  never resets"))

    parts.append(close_svg([]))
    return "\n".join(parts)


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
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
    out.mkdir(parents=True, exist_ok=True)
    hermes = load_hermes_tokens()
    nim_total = hermes.get("lifetime_total", 0)
    nim_sessions = hermes.get("sessions_count", 0)
    nim_updated = hermes.get("last_update", "")
    claude_map, sessions, cost = claude_tokens()
    claude_total = sum(sum(d.values()) for d in claude_map.values())

    svg = render(nim_total, nim_sessions, nim_updated, claude_total, sessions, cost)
    grand = nim_total + claude_total
    svg_path = out / "token-stats.svg"
    svg_path.write_text(svg)
    print(f"Token chart → {svg_path} ({len(svg)} bytes) "
          f"NIM={human(nim_total)} Claude={human(claude_total)} Total={human(grand)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
