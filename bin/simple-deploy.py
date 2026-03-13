#!/usr/bin/env python3
"""Deploy dotfiles via symlinks for non-Nix environments."""

import argparse
import os
import sys
from pathlib import Path

DEPLOY_MAP = [
    # (source_dir,                          dest_dir)
    ("home/modules/claude-code/files",      ".claude"),
    ("home/modules/git/files",              ".config/git"),
    ("home/modules/mise/files",             ".config/mise"),
    ("home/modules/nvim/files",             ".config/nvim"),
    ("home/modules/tmux/files",             ".config/tmux"),
    ("home/modules/uv/files",              ".config/uv"),
]


def get_repo_root() -> Path:
    root = Path(__file__).resolve().parent.parent
    if not (root / "home" / "modules").is_dir():
        print(f"ERROR: Cannot determine repo root. Expected 'home/modules/' at {root}", file=sys.stderr)
        sys.exit(1)
    return root


def expand_map(repo_root: Path, home: Path) -> list[tuple[Path, Path]]:
    pairs = []
    for source_dir, dest_dir in DEPLOY_MAP:
        source_abs = repo_root / source_dir
        if not source_abs.is_dir():
            continue
        for dirpath, _dirnames, filenames in os.walk(source_abs):
            for filename in filenames:
                source_file = Path(dirpath) / filename
                relative = source_file.relative_to(source_abs)
                dest_file = home / dest_dir / relative
                pairs.append((source_file, dest_file))
    return pairs


def preflight_check(pairs: list[tuple[Path, Path]]) -> list[str]:
    conflicts = []
    for source_abs, dest_abs in pairs:
        if dest_abs.exists() or dest_abs.is_symlink():
            suffix = " (symlink)" if dest_abs.is_symlink() else ""
            conflicts.append(f"  EXISTS  {dest_abs}{suffix}")
        else:
            for parent in dest_abs.parents:
                if parent == dest_abs.parent.root:
                    break
                if parent.is_file():
                    conflicts.append(f"  PARENT  {parent} is a regular file (expected directory)")
                    break
    return conflicts


def deploy(pairs: list[tuple[Path, Path]], dry_run: bool) -> None:
    for source_abs, dest_abs in pairs:
        print(f"LINK  {dest_abs} -> {source_abs}")

    if dry_run:
        return

    conflicts = preflight_check(pairs)
    if conflicts:
        print("\nERROR: Cannot deploy. The following conflicts were found:\n")
        for conflict in conflicts:
            print(conflict)
        print("\nResolve these conflicts manually, then re-run.")
        sys.exit(1)

    for source_abs, dest_abs in pairs:
        dest_abs.parent.mkdir(parents=True, exist_ok=True)
        dest_abs.symlink_to(source_abs)


def unlink(pairs: list[tuple[Path, Path]], home: Path, dry_run: bool) -> None:
    dirs_to_check = set()
    for source_abs, dest_abs in pairs:
        if dest_abs.is_symlink() and dest_abs.resolve() == source_abs.resolve():
            if dry_run:
                print(f"REMOVE  {dest_abs}")
            else:
                dest_abs.unlink()
                print(f"REMOVE  {dest_abs}")
            dirs_to_check.add(dest_abs.parent)

    # Collect all parent directories up to (but not including) $HOME
    all_dirs = set()
    for d in dirs_to_check:
        current = d
        while current != home and current != current.parent:
            all_dirs.add(current)
            current = current.parent

    # Sort deepest first for bottom-up cleanup
    for d in sorted(all_dirs, key=lambda p: len(p.parts), reverse=True):
        if d.is_dir() and not any(d.iterdir()):
            if dry_run:
                print(f"RMDIR  {d}")
            else:
                d.rmdir()
                print(f"RMDIR  {d}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Deploy dotfiles via symlinks for non-Nix environments."
    )
    parser.add_argument("--unlink", action="store_true",
                        help="Remove symlinks created by this script")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be done without making changes")
    args = parser.parse_args()

    repo_root = get_repo_root()
    home = Path.home()
    pairs = expand_map(repo_root, home)

    if args.unlink:
        unlink(pairs, home, args.dry_run)
    else:
        deploy(pairs, args.dry_run)


if __name__ == "__main__":
    main()
