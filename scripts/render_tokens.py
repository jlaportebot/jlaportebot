#!/usr/bin/env python3
"""Render token consumption: NVIDIA NIM vs Claude Code CLI vs Combined Total.

Three big clean cards at a glance, plus an organized Claude Code CLI per-model
breakdown below so it's obvious which models drove the usage.
"""
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from theme import (
    W, defs, canvas, close_svg, stat_card, panel,
    FONT, MONO, NVIDIA, ANTHROPIC, TOTAL, TEXT, TEXT_MUTED, TEXT_DIM, STROKE, BG_PANEL,
)

TOKEN_FILE = Path(__file__).parent.parent / "token_lifetime.json"
CLAUDE_DIR = Path.home() / ".claude" / "projects"

# Layout constants so nothing is cut off.
CANVAS_H = 620
CARDS_Y = 120
CARDS_H = 180
MODEL_HEADER_Y = 320
MODEL_SUB_Y = 336
TABLE_HEADER_Y = 358
ROW_START_Y = 376
ROW_H = 17


def load_hermes_tokens():
    """Read the lifetime NIM total from token_lifetime.json."""
    if not TOKEN_FILE.exists():
        return {"lifetime_total": 0, "sessions_count": 0, "last_update": ""}
    try:
        return json.loads(TOKEN_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return {"lifetime_total": 0, "sessions_count": 0, "last_update": ""}


def claude_tokens():
    """Aggregate Claude Code CLI token usage per model across all JSONL files."""
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


def pct(part, whole):
    if not whole:
        return "0.0%"
    return f"{100.0 * part / whole:.1f}%"


def render(nim_total, nim_sessions, nim_updated, claude_total, sessions, cost, per_model):
    grand = nim_total + claude_total
    nim_pct = pct(nim_total, grand)
    claude_pct = pct(claude_total, grand)

    parts = []
    parts.append(canvas(W, CANVAS_H, "t", "Lifetime Token Consumption",
                        "Hermes Agent (NVIDIA NIM) · Claude Code CLI · Combined",
                        f"Updated {nim_updated[:10] if nim_updated else ''}"))
    parts.append(defs("t"))

    cw = (W - 64 - 40) / 3  # card width for 3 across

    # Card 1: NVIDIA NIM
    parts.append(stat_card(32, CARDS_Y, cw, CARDS_H, "NVIDIA NIM (Hermes Agent)",
                           human(nim_total), NVIDIA,
                           value_size=32,
                           sublabel=f"{nim_sessions:,} sessions  •  {nim_pct} of total"))

    # Card 2: Claude Code CLI
    cx = 32 + cw + 20
    parts.append(stat_card(cx, CARDS_Y, cw, CARDS_H, "Claude Code CLI",
                           human(claude_total), ANTHROPIC,
                           value_size=32,
                           sublabel=f"{len(sessions)} sessions  •  ${cost:,.2f} cost  •  {claude_pct} of total"))

    # Card 3: Total
    tx = cx + cw + 20
    parts.append(stat_card(tx, CARDS_Y, cw, CARDS_H, "Combined Total",
                           human(grand), TOTAL,
                           value_size=34,
                           sublabel=f"NIM {human(nim_total)} + Claude {human(claude_total)}  •  never resets"))

    # --- Claude per-model breakdown -------------------------------------
    parts.append(
        f'  <text x="32" y="{MODEL_HEADER_Y}" fill="{TEXT}" font-size="14" font-weight="800" '
        f'font-family="{FONT}">Claude Code CLI — token use by model</text>'
    )
    parts.append(
        f'  <text x="32" y="{MODEL_SUB_Y}" fill="{TEXT_MUTED}" font-size="11" font-family="{FONT}">'
        f"sorted by total tokens · input / output / cache read / cache write</text>"
    )

    # Build sorted model rows: (model, total, in, out, cache_r, cache_w)
    rows = []
    for model, d in per_model.items():
        total = d["in"] + d["out"] + d["cache_r"] + d["cache_w"]
        rows.append((model, total, d["in"], d["out"], d["cache_r"], d["cache_w"]))
    rows.sort(key=lambda r: -r[1])

    # Table header
    hx = [32, 300, 420, 520, 620, 720, 860]
    headers = [("Model", False), ("Total", True), ("Input", True),
               ("Output", True), ("Cache R", True), ("Cache W", True)]
    y = TABLE_HEADER_Y
    for i, (label, right) in enumerate(headers):
        anchor = "end" if right else "start"
        parts.append(f'  <text x="{hx[i]}" y="{y}" fill="{TEXT_MUTED}" font-size="10" '
                     f'font-weight="700" font-family="{MONO}" text-anchor="{anchor}">{label}</text>')

    # Rows (top 8 to keep it readable)
    show = rows[:8]
    for i, (model, total, inp, outp, cachr, cachw) in enumerate(show):
        ry = ROW_START_Y + ROW_H * i
        disp = model
        if len(disp) > 34:
            disp = disp[:31] + "..."
        parts.append(f'  <text x="{hx[0]}" y="{ry}" fill="{TEXT}" font-size="10.5" font-family="{MONO}">{disp}</text>')
        parts.append(f'  <text x="{hx[1]}" y="{ry}" fill="{TEXT}" font-size="10.5" font-weight="700" font-family="{MONO}" text-anchor="end">{human(total)}</text>')
        parts.append(f'  <text x="{hx[2]}" y="{ry}" fill="{TEXT_DIM}" font-size="10" font-family="{MONO}" text-anchor="end">{human(inp)}</text>')
        parts.append(f'  <text x="{hx[3]}" y="{ry}" fill="{TEXT_DIM}" font-size="10" font-family="{MONO}" text-anchor="end">{human(outp)}</text>')
        parts.append(f'  <text x="{hx[4]}" y="{ry}" fill="{TEXT_DIM}" font-size="10" font-family="{MONO}" text-anchor="end">{human(cachr)}</text>')
        parts.append(f'  <text x="{hx[5]}" y="{ry}" fill="{TEXT_DIM}" font-size="10" font-family="{MONO}" text-anchor="end">{human(cachw)}</text>')

    if len(rows) > 8:
        rest_total = sum(r[1] for r in rows[8:])
        ry = ROW_START_Y + ROW_H * len(show)
        parts.append(f'  <text x="{hx[0]}" y="{ry}" fill="{TEXT_MUTED}" font-size="10" font-family="{MONO}">+{len(rows)-8} more models</text>')
        parts.append(f'  <text x="{hx[1]}" y="{ry}" fill="{TEXT_MUTED}" font-size="10" font-weight="700" font-family="{MONO}" text-anchor="end">{human(rest_total)}</text>')

    # Footnote: share of grand total (positioned below last row with margin)
    last_row_y = ROW_START_Y + ROW_H * len(show)
    fy = last_row_y + ROW_H + 16
    claude_share = pct(claude_total, grand) if grand else "0.0%"
    parts.append(
        f'  <text x="32" y="{fy}" fill="{TEXT_MUTED}" font-size="10" font-family="{MONO}">'
        f"Claude = {claude_share} of grand total · {len(sessions)} sessions · ${cost:,.2f} cost</text>"
    )

    parts.append(close_svg([]))
    return "\n".join(parts)


def main():
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
    out.mkdir(parents=True, exist_ok=True)
    hermes = load_hermes_tokens()
    nim_total = hermes.get("lifetime_total", 0)
    nim_sessions = hermes.get("sessions_count", 0)
    nim_updated = hermes.get("last_update", "")
    claude_map, sessions, cost = claude_tokens()
    claude_total = sum(d["in"] + d["out"] + d["cache_r"] + d["cache_w"] for d in claude_map.values())

    svg = render(nim_total, nim_sessions, nim_updated, claude_total, sessions, cost, claude_map)
    svg_path = out / "token-stats.svg"
    svg_path.write_text(svg)
    grand = nim_total + claude_total
    print(f"Token chart → {svg_path} ({len(svg)} bytes) "
          f"NIM={human(nim_total)} Claude={human(claude_total)} Total={human(grand)} "
          f"models={len(claude_map)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
