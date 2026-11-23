#!/usr/bin/env python3
import json
import subprocess
import sys

RESET = "\x1b[0m"
DIM = "\x1b[2m"
BOLD = "\x1b[1m"
WHITE = "\x1b[38;2;255;255;255m"
GREEN = "\x1b[38;2;0;200;80m"
YELLOW = "\x1b[38;2;255;200;60m"
RED = "\x1b[38;2;255;0;60m"

ICON_FOLDER = "\U0001F4C2"

RINGS = ["○", "◔", "◑", "◕", "●"]


def format_tokens(tokens: int) -> str:
    if tokens >= 1_000_000:
        v = tokens / 1_000_000
        return f"{v:.0f}M" if v.is_integer() else f"{v:.1f}M"
    if tokens >= 1_000:
        v = tokens / 1_000
        return f"{v:.0f}K" if v.is_integer() else f"{v:.1f}K"
    return str(tokens)


def threshold_color(value: float, warn: float, crit: float) -> str:
    if value < warn:
        return GREEN
    if value < crit:
        return YELLOW
    return RED


def ring(pct: float) -> str:
    idx = min(int(pct / 25), 4)
    return RINGS[idx]


def fmt_meter(pct: float, used: int, total: int) -> str:
    p = round(pct)
    color = threshold_color(pct, 50, 80)
    size = f"{format_tokens(used)}/{format_tokens(total)}"
    return f"{color}{ring(pct)} {size} ({p}%){RESET}"


def git_branch(cwd: str) -> str | None:
    result = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def main() -> None:
    data = json.loads(sys.stdin.read())
    model = data["model"]["display_name"]
    cwd = data["workspace"]["current_dir"]
    location = f"{ICON_FOLDER} {YELLOW}{cwd}{RESET}"
    branch = git_branch(cwd)
    if branch:
        location += f" {DIM}@{RESET} {GREEN}{branch}{RESET}"

    segments = [
        f"{BOLD}{WHITE}{model}{RESET}",
        location,
    ]

    try:
        tokens = sum(data["context_window"]["current_usage"].values())
        window_size = data["context_window"]["context_window_size"]
        if window_size > 0:
            pct = tokens / window_size * 100
            segments.append(fmt_meter(pct, tokens, window_size))
    except Exception:
        pass  # NOTE(himkt): usage metrics not available on startup.

    print(f" {DIM}|{RESET} ".join(segments))


if __name__ == "__main__":
    main()
