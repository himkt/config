#!/usr/bin/env python3
import json
import os
import re
import sys

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


def format_tokens(tokens: int) -> str:
    if tokens >= 1_000_000:
        v = tokens / 1_000_000
        return f"{v:.0f}M" if v == int(v) else f"{v:.1f}M"
    if tokens >= 1_000:
        v = tokens / 1_000
        return f"{v:.0f}K" if v == int(v) else f"{v:.1f}K"
    return str(tokens)


def gradient_color(position: float) -> str:
    """Return true color (24-bit) ANSI code for position 0.0 (green) to 1.0 (red)."""
    position = max(0.0, min(1.0, position))
    for i in range(len(GRADIENT_STOPS) - 1):
        t0, rgb0 = GRADIENT_STOPS[i]
        t1, rgb1 = GRADIENT_STOPS[i + 1]
        if position <= t1:
            t = (position - t0) / (t1 - t0) if t1 > t0 else 0.0
            r = int(rgb0[0] + (rgb1[0] - rgb0[0]) * t)
            g = int(rgb0[1] + (rgb1[1] - rgb0[1]) * t)
            b = int(rgb0[2] + (rgb1[2] - rgb0[2]) * t)
            return f"\x1b[38;2;{r};{g};{b}m"
    _, rgb = GRADIENT_STOPS[-1]
    return f"\x1b[38;2;{rgb[0]};{rgb[1]};{rgb[2]}m"


def build_context_bar(
    current_usage: int,
    context_window_size: int,
    max_output_tokens: int,
) -> tuple[str, int]:
    """Build a colored progress bar. Returns (bar_text, buffer_offset, usable_space)."""
    usable_space = context_window_size - max_output_tokens
    effective_pct = (current_usage / usable_space * 100) if usable_space > 0 else 100.0
    raw_pct = round(current_usage / context_window_size * 100)

    # Segment widths
    buffer_chars = max(1, min(BAR_WIDTH - 1, round(max_output_tokens / context_window_size * BAR_WIDTH)))
    used_chars = max(0, min(BAR_WIDTH, round(current_usage / context_window_size * BAR_WIDTH)))
    if used_chars + buffer_chars > BAR_WIDTH:
        buffer_chars = max(0, BAR_WIDTH - used_chars)
    free_chars = BAR_WIDTH - used_chars - buffer_chars

    # Build bar string with per-character gradient
    used_part = ""
    for i in range(used_chars):
        pos = i / max(BAR_WIDTH - 1, 1)
        used_part += f"{gradient_color(pos)}█"
    bar = (
        f"[{used_part}{RESET}"
        f"{DIM}{'░' * (free_chars + buffer_chars)}{RESET}]"
    )

    used_str = format_tokens(current_usage)
    total_str = format_tokens(context_window_size)
    text_color = gradient_color(min(effective_pct / 100, 1.0))
    bar_text = f"{bar} {text_color}{used_str}/{total_str} ({raw_pct}%){RESET}"

    # Offset to buffer boundary (fixed position regardless of usage)
    original_buffer_chars = max(1, min(BAR_WIDTH - 1, round(max_output_tokens / context_window_size * BAR_WIDTH)))
    buffer_offset = 1 + BAR_WIDTH - original_buffer_chars
    return bar_text, buffer_offset, usable_space


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

    bar_text = None
    try:
        tokens = sum(data["context_window"]["current_usage"].values())
        window_size = data["context_window"]["context_window_size"]
        bar_text, buffer_offset, usable_space = build_context_bar(tokens, window_size, max_output_tokens)
    except Exception:
        pass  # NOTE(himkt): usage metrics not available on startup.

    if bar_text is not None:
        elements.append(bar_text)
    print(f" {DIM}|{RESET} ".join(elements))

    if bar_text is not None:
        sep = f" {DIM}|{RESET} "
        prefix = sep.join(elements[:-1]) + sep
        prefix_width = len(re.sub(r"\x1b\[[0-9;]*m", "", prefix))
        total_pad = prefix_width + buffer_offset
        usable_label = format_tokens(usable_space)
        pad = "\u2800" * total_pad
        print(f"{pad}{ACCENT}▲ autocompact ({usable_label}){RESET}")


if __name__ == "__main__":
    main()
