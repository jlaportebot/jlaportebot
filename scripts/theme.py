#!/usr/bin/env python3
"""Clean, readable design system for jlaportebot profile visuals.

Art style: soft abyssal canvas, subtle gradient glows, clean glass cards,
high-contrast typography, one accent color per metric. Built for readability
at a glance on GitHub profile READMEs.
"""

# --- Palette ---------------------------------------------------------------

BG = "#0b1120"          # deep abyssal canvas
BG_PANEL = "#111930"    # card surface
STROKE = "#273254"      # subtle borders

TEXT = "#eef2fb"        # primary text (near-white)
TEXT_MUTED = "#93a3c1"  # secondary text
TEXT_DIM = "#6270a1"    # tertiary text

CYAN = "#22d3ee"
VIOLET = "#a78bfa"
PINK = "#f472b6"
AMBER = "#fbbf24"
EMERALD = "#34d399"
ROSE = "#fb7185"

NVIDIA = "#76b900"      # green (NVIDIA NIM)
ANTHROPIC = "#d97757"   # warm (Claude)
TOTAL = "#22d3ee"       # cyan (combined)

FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Inter,Helvetica,Arial,sans-serif"
MONO = "'SFMono-Regular',Menlo,Consolas,'Liberation Mono',monospace"

W = 960


# --- Primitives ------------------------------------------------------------


def esc(text):
    """Escape XML-sensitive characters using numeric character codes."""
    text = str(text)
    amp = chr(38)
    names = {38: "amp;", 60: "lt;", 62: "gt;", 34: "quot;", 39: "apos;"}
    for code, name in names.items():
        text = text.replace(chr(code), amp + name)
    return text


def defs(prefix):
    """Shared gradients + a soft glow filter."""
    parts = ["  <defs>"]
    parts.append(
        f'    <linearGradient id="{prefix}bg" x1="0%" y1="0%" x2="0%" y2="100%">'
        f'<stop offset="0%" stop-color="{BG}"/>'
        f'<stop offset="60%" stop-color="#101a30"/>'
        f'<stop offset="100%" stop-color="{BG}"/></linearGradient>'
    )
    parts.append(
        f'    <radialGradient id="{prefix}glow" cx="50%" cy="50%" r="70%">'
        f'<stop offset="0%" stop-color="#23305b" stop-opacity="0.25"/>'
        f'<stop offset="100%" stop-color="#23305b" stop-opacity="0"/></radialGradient>'
    )
    parts.append(
        f'    <filter id="{prefix}soft" x="-20%" y="-20%" width="140%" height="140%">'
        f'<feGaussianBlur stdDeviation="6" result="b"/>'
        f'<feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>'
        f'</filter>'
    )
    parts.append("  </defs>")
    return "\n".join(parts)


def canvas(width, height, prefix, title=None, subtitle=None, updated=None):
    """Open the SVG document with the gradient canvas."""
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'width="{width}" height="{height}" role="img" aria-label="{esc(title or "")}">',
        defs(prefix),
        f'  <rect width="{width}" height="{height}" rx="18" fill="url(#{prefix}bg)"/>',
        f'  <rect width="{width}" height="{height}" rx="18" fill="url(#{prefix}glow)"/>',
        f'  <rect width="{width}" height="{height}" rx="18" fill="none" stroke="{STROKE}" stroke-width="1"/>',
    ]
    y = 36
    if title:
        out.append(
            f'  <text x="32" y="{y}" fill="{TEXT}" font-size="17" font-weight="800" '
            f'font-family="{FONT}">{esc(title)}</text>'
        )
        y += 24
    if subtitle:
        out.append(
            f'  <text x="32" y="{y}" fill="{TEXT_MUTED}" font-size="12" font-family="{FONT}">{esc(subtitle)}</text>'
        )
        y += 18
    if updated:
        out.append(
            f'  <text x="{width - 32}" y="34" fill="{TEXT_DIM}" font-size="11" '
            f'text-anchor="end" font-family="{MONO}">{esc(updated)}</text>'
        )
    return "\n".join(out)


def close_svg(parts):
    parts.append("</svg>")
    return "\n".join(parts)


def panel(x, y, w, h, accent=None, prefix="p"):
    """A clean rounded card."""
    out = [
        f'  <rect x="{x}" y="{y}" width="{w}" height="{h}" rx="14" '
        f'fill="{BG_PANEL}" stroke="{STROKE}" stroke-width="1"/>',
    ]
    if accent:
        out.append(
            f'  <rect x="{x}" y="{y}" width="{w}" height="{h}" rx="14" fill="none" '
            f'stroke="{accent}" stroke-opacity="0.35" stroke-width="1"/>'
        )
    return "\n".join(out)


def stat_card(x, y, w, h, label, value, accent, value_size=34, sublabel=None):
    """A big-number metric card — label above, value below, accent strip."""
    out = [panel(x, y, w, h, accent)]
    # Wrap long labels so they stay inside the card box instead of overflowing.
    label_lines = wrap_text(label.upper(), max_chars=32)
    label_y = y + 28
    for line in label_lines:
        out.append(
            f'  <text x="{x + 24}" y="{label_y}" fill="{TEXT_MUTED}" font-size="11.5" '
            f'font-weight="700" font-family="{FONT}" letter-spacing="1.2">{esc(line)}</text>'
        )
        label_y += 15
    out.append(
        f'  <rect x="{x + 24}" y="{label_y + 6}" width="24" height="4" rx="2" fill="{accent}"/>'
    )
    out.append(
        f'  <text x="{x + 24}" y="{label_y + 6 + value_size + 12}" fill="{TEXT}" '
        f'font-size="{value_size}" font-weight="800" font-family="{FONT}">{esc(value)}</text>'
    )
    if sublabel:
        out.append(
            f'  <text x="{x + 24}" y="{y + h - 20}" fill="{TEXT_DIM}" font-size="10.5" '
            f'font-family="{MONO}">{esc(sublabel)}</text>'
        )
    return "\n".join(out)


def wrap_text(text, max_chars=38):
    """Break a label into lines that fit within a stat card.

    SVG has no automatic text wrapping, so we split on spaces and wrap
    at max_chars per line. Long words are split forcefully if needed.
    """
    words = text.split()
    if not words:
        return [""]
    lines = []
    current = ""
    for word in words:
        candidate = (current + " " + word).strip()
        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                lines.append(current)
            # Force-split words longer than max_chars
            while len(word) > max_chars:
                lines.append(word[:max_chars])
                word = word[max_chars:]
            current = word
    if current:
        lines.append(current)
    return lines


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


def group(n):
    return f"{int(n):,}"


def pct(part, whole):
    if not whole:
        return "0.0%"
    return f"{100.0 * part / whole:.1f}%"
