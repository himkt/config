#!/usr/bin/env python3
import json
import os
import sys

RESET = "\x1b[0m"
DIM = "\x1b[2m"
RED = "\x1b[31m"
YELLOW = "\x1b[33m"
GREEN = "\x1b[32m"
YELLOW_GREEN = "\x1b[38;5;142m"
ORANGE = "\x1b[38;5;208m"
BUFFER_STYLE = "\x1b[97;45m"
BAR_WIDTH = 20
DEFAULT_MAX_OUTPUT_TOKENS = 32000


def format_tokens(tokens: int) -> str:
    if tokens >= 1_000_000:
        v = tokens / 1_000_000
        return f"{v:.0f}M" if v == int(v) else f"{v:.1f}M"
    if tokens >= 1_000:
        v = tokens / 1_000
        return f"{v:.0f}K" if v == int(v) else f"{v:.1f}K"
    return str(tokens)


def context_color(percentage: float) -> str:
    if percentage >= 90:
        return RED
    if percentage >= 80:
        return ORANGE
    if percentage >= 60:
        return YELLOW
    if percentage >= 40:
        return YELLOW_GREEN
    return GREEN


def build_context_bar(
    current_usage: int,
    context_window_size: int,
    max_output_tokens: int,
) -> str:
    """Build a colored progress bar showing context window usage."""
    usable_space = context_window_size - max_output_tokens
    effective_pct = (current_usage / usable_space * 100) if usable_space > 0 else 100.0
    raw_pct = round(current_usage / context_window_size * 100)

    # Segment widths
    buffer_chars = max(1, min(BAR_WIDTH - 1, round(max_output_tokens / context_window_size * BAR_WIDTH)))
    used_chars = max(0, min(BAR_WIDTH, round(current_usage / context_window_size * BAR_WIDTH)))
    if used_chars + buffer_chars > BAR_WIDTH:
        buffer_chars = max(0, BAR_WIDTH - used_chars)
    free_chars = BAR_WIDTH - used_chars - buffer_chars

    # Build bar string
    color = context_color(effective_pct)
    bar = (
        f"[{color}{'█' * used_chars}{RESET}"
        f"{DIM}{'░' * free_chars}{RESET}"
        f"{BUFFER_STYLE}{'▒' * buffer_chars}{RESET}]"
    )

    used_str = format_tokens(current_usage)
    total_str = format_tokens(context_window_size)
    return f"{bar} {used_str}/{total_str} ({raw_pct}%)"


def main() -> None:
    data = json.loads(sys.stdin.read())
    model = data["model"]["display_name"]
    cwd = data["workspace"]["current_dir"]
    cost = data["cost"]["total_cost_usd"]
    max_output_tokens = int(os.environ.get("CLAUDE_CODE_MAX_OUTPUT_TOKENS", str(DEFAULT_MAX_OUTPUT_TOKENS)))

    elements = [
        f"{DIM}{model}{RESET}",
        f"📁 {cwd}",
        f"💰 ${cost:.4f}",
    ]

    try:
        tokens = sum(data["context_window"]["current_usage"].values())
        window_size = data["context_window"]["context_window_size"]
        elements.append(build_context_bar(tokens, window_size, max_output_tokens))
    except Exception:
        pass  # NOTE(himkt): usage metrics not available on startup.

    print(f" {DIM}|{RESET} ".join(elements))


if __name__ == "__main__":
    main()
