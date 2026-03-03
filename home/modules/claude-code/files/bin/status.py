#!/usr/bin/env python3
import json
import os
import re
import sys
from typing import NamedTuple

RESET = "\x1b[0m"
DIM = "\x1b[2m"
ACCENT = "\x1b[38;2;180;160;80m"
BAR_WIDTH = 20
DEFAULT_MAX_OUTPUT_TOKENS = 32000

# True Color gradient stops: green → yellow → red
GRADIENT_STOPS = [
    (0.0, (80, 200, 120)),   # green
    (0.5, (255, 220, 50)),   # yellow
    (1.0, (255, 70, 70)),    # red
]

# Nerd Font icons
ICON_FOLDER = "\uf07c"
ICON_DOLLAR = "\uf155"

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


class ContextBar(NamedTuple):
    text: str
    buffer_offset: int
    usable_space: int


def _rgb_fg(r: int, g: int, b: int) -> str:
    return f"\x1b[38;2;{r};{g};{b}m"


def _strip_ansi(s: str) -> str:
    return _ANSI_RE.sub("", s)


def format_tokens(tokens: int) -> str:
    if tokens >= 1_000_000:
        v = tokens / 1_000_000
        return f"{v:.0f}M" if v.is_integer() else f"{v:.1f}M"
    if tokens >= 1_000:
        v = tokens / 1_000
        return f"{v:.0f}K" if v.is_integer() else f"{v:.1f}K"
    return str(tokens)


def gradient_color(position: float) -> str:
    """Return true color (24-bit) ANSI code for position 0.0 (green) to 1.0 (red)."""
    position = max(0.0, min(1.0, position))
    for (t0, rgb0), (t1, rgb1) in zip(GRADIENT_STOPS, GRADIENT_STOPS[1:]):
        if position <= t1:
            t = (position - t0) / (t1 - t0) if t1 > t0 else 0.0
            r, g, b = (int(c0 + (c1 - c0) * t) for c0, c1 in zip(rgb0, rgb1))
            return _rgb_fg(r, g, b)
    _, (r, g, b) = GRADIENT_STOPS[-1]
    return _rgb_fg(r, g, b)


def build_context_bar(
    current_usage: int,
    context_window_size: int,
    max_output_tokens: int,
) -> ContextBar:
    """Build a colored progress bar with context usage information."""
    usable_space = context_window_size - max_output_tokens
    usage_ratio = current_usage / context_window_size if context_window_size > 0 else 1.0
    effective_ratio = current_usage / usable_space if usable_space > 0 else 1.0
    raw_pct = round(usage_ratio * 100)

    # Segment widths
    buffer_chars = max(1, min(BAR_WIDTH - 1, round(max_output_tokens / context_window_size * BAR_WIDTH)))
    used_chars = max(0, min(BAR_WIDTH, round(usage_ratio * BAR_WIDTH)))
    buffer_offset = 1 + BAR_WIDTH - buffer_chars
    if used_chars + buffer_chars > BAR_WIDTH:
        buffer_chars = max(0, BAR_WIDTH - used_chars)
    free_chars = BAR_WIDTH - used_chars - buffer_chars

    # Build bar string with per-character gradient
    used_part = "".join(
        f"{gradient_color(i / max(BAR_WIDTH - 1, 1))}█"
        for i in range(used_chars)
    )
    bar = f"[{used_part}{RESET}{DIM}{'░' * (free_chars + buffer_chars)}{RESET}]"

    used_str = format_tokens(current_usage)
    total_str = format_tokens(context_window_size)
    text_color = gradient_color(min(effective_ratio, 1.0))
    text = f"{bar} {text_color}{used_str}/{total_str} ({raw_pct}%){RESET}"

    return ContextBar(text, buffer_offset, usable_space)


def main() -> None:
    data = json.loads(sys.stdin.read())
    model = data["model"]["display_name"]
    cwd = data["workspace"]["current_dir"]
    cost = data["cost"]["total_cost_usd"]
    max_output_tokens = int(os.environ.get("CLAUDE_CODE_MAX_OUTPUT_TOKENS", str(DEFAULT_MAX_OUTPUT_TOKENS)))

    elements = [
        f"{DIM}{model}{RESET}",
        f"{ICON_FOLDER} {cwd}",
        f"{ICON_DOLLAR} {cost:.4f}",
    ]

    bar: ContextBar | None = None
    try:
        tokens = sum(data["context_window"]["current_usage"].values())
        window_size = data["context_window"]["context_window_size"]
        bar = build_context_bar(tokens, window_size, max_output_tokens)
    except Exception:
        pass  # NOTE(himkt): usage metrics not available on startup.

    if bar is not None:
        elements.append(bar.text)

    sep = f" {DIM}|{RESET} "
    print(sep.join(elements))

    if bar is not None:
        prefix_width = len(_strip_ansi(sep.join(elements[:-1]) + sep))
        pad = "\u2800" * (prefix_width + bar.buffer_offset)
        usable_label = format_tokens(bar.usable_space)
        print(f"{pad}{ACCENT}▲ autocompact ({usable_label}){RESET}")


if __name__ == "__main__":
    main()
