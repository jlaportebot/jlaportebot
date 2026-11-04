#!/usr/bin/env python3
"""Shared design system for jlaportebot profile visuals.

One cohesive art style across every SVG: abyssal-navy gradient canvas,
aurora blooms, glass cards, neon accents, and a consistent type scale.
Everything here is pure string building — no side effects, no I/O.
"""

# --- Palette ---------------------------------------------------------------

BG_DEEP = "#070b18"
BG_MID = "#0d1428"
BG_BLOOM_A = "#3b1f6b"
BG_BLOOM_B = "#0d3b58"
CARD = "#0f1830"
CARD_HI = "#142040"
STROKE = "#223154"
STROKE_HI = "#33456f"
TEXT = "#e9eefb"
TEXT_DIM = "#8d9cc4"
TEXT_FAINT = "#5b6a90"

CYAN = "#22d3ee"
VIOLET = "#a78bfa"
PINK = "#f472b6"
AMBER = "#fbbf24"
EMERALD = "#34d399"
ROSE = "#fb7185"

NVIDIA = "#76b900"
ANTHROPIC = "#d97757"

FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Inter,Helvetica,Arial,sans-serif"
MONO = "'SFMono-Regular',Menlo,Consolas,'Liberation Mono',monospace"

SERIES = {
    "repos": "#f78166",
    "opened": "#58a6ff",
    "open": "#3fb950",
    "merged": "#d2a8ff",
    "closed": "#f85149",
}

CANVAS_W = 960
W = CANVAS_W


# --- Primitives ------------------------------------------------------------


def defs(prefix, blooms=True):
    """SVG <defs> with gradients, filters and glow shared by every visual."""
    parts = ["  <defs>"]
    parts.append(
        f'    <linearGradient id="{prefix}bg" x1="0%" y1="0%" x2="100%" y2="100%">'
        f'<stop offset="0%" stop-color="{BG_DEEP}"/>'
        f'<stop offset="55%" stop-color="{BG_MID}"/>'
        f'<stop offset="100%" stop-color="{BG_DEEP}"/></linearGradient>'
    )
    if blooms:
        parts.append(
            f'    <radialGradient id="{prefix}bloomA" cx="18%" cy="8%" r="62%">'
            f'<stop offset="0%" stop-color="{BG_BLOOM_A}" stop-opacity="0.75"/>'
            f'<stop offset="100%" stop-color="{BG_BLOOM_A}" stop-opacity="0"/></radialGradient>'
        )
        parts.append(
            f'    <radialGradient id="{prefix}bloomB" cx="88%" cy="92%" r="58%">'
            f'<stop offset="0%" stop-color="{BG_BLOOM_B}" stop-opacity="0.65"/>'
            f'<stop offset="100%" stop-color="{BG_BLOOM_B}" stop-opacity="0"/></radialGradient>'
        )
    parts.append(
        f'    <linearGradient id="sheen" x1="0%" y1="0%" x2="0%" y2="100%">'
        f'<stop offset="0%" stop-color="#ffffff" stop-opacity="0.07"/>'
        f'<stop offset="100%" stop-color="#ffffff" stop-opacity="0"/></linearGradient>'
    )
    parts.append(
        f'    <filter id="glow" x="-40%" y="-40%" width="180%" height="180%">'
        f'<feGaussianBlur stdDeviation="4" result="b"/>'
        f'<feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>'
        f'</filter>'
    )
    parts.append("  </defs>")
    return "\n".join(parts)


def canvas(width, height, prefix, title, subtitle=None, updated=None):
    """Open the SVG document, paint the gradient canvas and the header."""
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'width="{width}" height="{height}" role="img" aria-label="{title}">',
        defs(prefix),
        f'  <rect width="{width}" height="{height}" rx="16" fill="url(#{prefix}bg)"/>',
    ]
    if prefix:
        out.append(f'  <rect width="{width}" height="{height}" rx="16" fill="url(#{prefix}bloomA)"/>')
        out.append(f'  <rect width="{width}" height="{height}" rx="16" fill="url(#{prefix}bloomB)"/>')
    out.append(f'  <rect width="{width}" height="{height}" rx="16" fill="none" stroke="{STROKE}" stroke-width="1"/>')

    out.append(
        f'  <text x="28" y="34" fill="{TEXT}" font-size="16" font-weight="700" '
        f'font-family="{FONT}" letter-spacing="0.4">{title}</text>'
    )
    if subtitle:
        out.append(
            f'  <text x="28" y="52" fill="{TEXT_DIM}" font-size="11.5" '
            f'font-family="{FONT}">{subtitle}</text>'
        )
    if updated:
        out.append(
            f'  <text x="{width - 28}" y="34" fill="{TEXT_FAINT}" font-size="10.5" '
            f'text-anchor="end" font-family="{MONO}">{updated}</text>'
        )
    return "\n".join(out)


def close_svg(parts):
    """Close the SVG document."""
    parts.append("</svg>")
    return "\n".join(parts)


def card(x, y, w, h, accent=None, prefix="c"):
    """A glass panel with an optional neon accent bar along its left edge."""
    out = [
        f'  <rect x="{x}" y="{y}" width="{w}" height="{h}" rx="12" '
        f'fill="{CARD}" fill-opacity="0.82" stroke="{STROKE}" stroke-width="1"/>',
        f'  <rect x="{x}" y="{y}" width="{w}" height="{h}" rx="12" fill="url(#sheen)"/>',
    ]
    if accent:
        out.append(
            f'  <rect x="{x}" y="{y + 12}" width="3" height="{h - 24}" rx="1.5" '
            f'fill="{accent}" opacity="0.9"/>'
        )
    return "\n".join(out)


def stat_card(x, y, w, h, label, value, accent, sublabel=None, prefix="c", value_size=26):
    """A labelled metric card: caption, big value, optional footnote."""
    out = [card(x, y, w, h, accent, prefix)]
    pad = 18
    if accent:
        pad = 22
    out.append(
        f'  <text x="{x + pad}" y="{y + 24}" fill="{TEXT_DIM}" font-size="10.5" '
        f'font-family="{FONT}" font-weight="600" letter-spacing="1.1">'
        f'{label.upper()}</text>'
    )
    out.append(
        f'  <text x="{x + pad}" y="{y + 24 + value_size + 4}" fill="{TEXT}" '
        f'font-size="{value_size}" font-weight="800" font-family="{FONT}">{value}</text>'
    )
    if sublabel:
        out.append(
            f'  <text x="{x + pad}" y="{y + h - 12}" fill="{TEXT_FAINT}" font-size="10" '
            f'font-family="{MONO}">{sublabel}</text>'
        )
    return "\n".join(out)


def legend(x, y, items, size=11, gap=150):
    """Horizontal legend row: (label, color) pairs."""
    out = []
    for idx, (label, color) in enumerate(items):
        lx = x + idx * gap
        out.append(
            f'  <circle cx="{lx + 5}" cy="{y - 3}" r="4" fill="{color}" '
            f'filter="url(#glow)"/>'
        )
        out.append(
            f'  <text x="{lx + 15}" y="{y}" fill="{TEXT_DIM}" font-size="{size}" '
            f'font-family="{FONT}">{label}</text>'
        )
    return "\n".join(out)


def chip(x, y, text, color, prefix="c", size=10.5, pad=9, height=22):
    """A small pill-shaped label."""
    width = len(text) * (size * 0.62) + pad * 2
    out = [
        f'  <rect x="{x}" y="{y}" width="{width:.0f}" height="{height}" rx="{height / 2}" '
        f'fill="{color}" fill-opacity="0.14" stroke="{color}" stroke-opacity="0.45" stroke-width="1"/>',
        f'  <text x="{x + width / 2:.0f}" y="{y + height / 2 + 3.5:.0f}" fill="{color}" '
        f'font-size="{size}" font-weight="600" text-anchor="middle" font-family="{FONT}">{text}</text>',
    ]
    return "\n".join(out), width


def bar(x, y, w, h, value, maximum, color, track=STROKE):
    """A horizontal progress bar with a rounded fill."""
    frac = 0 if not maximum else max(0.0, min(1.0, value / maximum))
    out = [
        f'  <rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{h / 2}" fill="{track}" fill-opacity="0.55"/>'
    ]
    if frac > 0:
        out.append(
            f'  <rect x="{x}" y="{y}" width="{max(w * frac, h):.1f}" height="{h}" rx="{h / 2}" fill="{color}"/>'
        )
    return "\n".join(out)


# --- Formatting ------------------------------------------------------------


def human(n):
    """Compact human-readable count: 20524695971 -> 20.52B."""
    if n is None:
        return "0"
    n = float(n)
    for limit, suffix in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")):
        if abs(n) >= limit:
            val = n / limit
            text = f"{val:.2f}".rstrip("0").rstrip(".")
            return f"{text}{suffix}"
    return str(int(n))


def group(n):
    """Thousands-separated integer."""
    return f"{int(n):,}"


def pct(part, whole):
    """Percentage with one decimal, guarding divide-by-zero."""
    if not whole:
        return "0.0%"
    return f"{100.0 * part / whole:.1f}%"


def esc(text):
    """Escape XML-sensitive characters."""
    text = str(text)
    amp = chr(38)
    names = {38: "amp;", 60: "lt;", 62: "gt;", 34: "quot;", 39: "apos;"}
    for code, name in names.items():
        text = text.replace(chr(code), amp + name)
    return text
