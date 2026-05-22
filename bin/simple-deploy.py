#!/usr/bin/env python3
import argparse
import os
import sys
from pathlib import Path

DEPLOY_MAP = [
    ("home/modules/claude/files", ".claude", True),
    ("home/modules/git/files", ".config/git", False),
    ("home/modules/mise/files", ".config/mise", False),
    ("home/modules/nvim/files", ".config/nvim", False),
    ("home/modules/tmux/files", ".config/tmux", False),
    ("home/modules/uv/files", ".config/uv", False),
]


def get_repo_root() -> Path:
    root = Path(__file__).resolve().parent.parent
    if not (root / "home" / "modules").is_dir():
        sys.exit(f"ERROR: Cannot determine repo root. Expected 'home/modules/' at {root}")
    return root


def expand_map(repo_root: Path, home: Path, nix_unsupported_only: bool) -> list[tuple[Path, Path]]:
    pairs = []
    for source_dir, dest_dir, nix_supported in DEPLOY_MAP:
        if nix_unsupported_only and not nix_supported:
            continue
        src = repo_root / source_dir
        if not src.is_dir():
            continue
        for dirpath, _, filenames in os.walk(src):
            for f in filenames:
                source_file = Path(dirpath) / f
                pairs.append((source_file, home / dest_dir / source_file.relative_to(src)))
    return pairs


def preflight_check(pairs: list[tuple[Path, Path]]) -> list[str]:
    conflicts = []
    for _, dest in pairs:
        if dest.exists() or dest.is_symlink():
            conflicts.append(f"  EXISTS  {dest}{' (symlink)' if dest.is_symlink() else ''}")
        else:
            for parent in dest.parents:
                if parent == dest.parent.root:
                    break
                if parent.is_file():
                    conflicts.append(f"  PARENT  {parent} is a regular file (expected directory)")
                    break
    return conflicts


def deploy(pairs: list[tuple[Path, Path]], dry_run: bool) -> None:
    for src, dest in pairs:
        print(f"LINK  {dest} -> {src}")

    if conflicts := preflight_check(pairs):
        print("\nERROR: Cannot deploy. The following conflicts were found:\n")
        print("\n".join(conflicts))
        sys.exit("\nResolve these conflicts manually, then re-run.")

    if dry_run:
        return

    for src, dest in pairs:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.symlink_to(src)


def unlink(pairs: list[tuple[Path, Path]], home: Path, dry_run: bool) -> None:
    removed_dirs = set()
    for src, dest in pairs:
        if dest.is_symlink() and dest.resolve() == src.resolve():
            print(f"REMOVE  {dest}")
            if not dry_run:
                dest.unlink()
            removed_dirs.add(dest.parent)

    all_dirs = set()
    for d in removed_dirs:
        while d != home and d != d.parent:
            all_dirs.add(d)
            d = d.parent

    for d in sorted(all_dirs, key=lambda p: len(p.parts), reverse=True):
        if d.is_dir() and not any(d.iterdir()):
            print(f"RMDIR  {d}")
            if not dry_run:
                d.rmdir()


def main() -> None:
    parser = argparse.ArgumentParser(description="Deploy dotfiles via symlinks for non-Nix environments.")
    parser.add_argument("--unlink", action="store_true", help="Remove symlinks created by this script")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without making changes")
    parser.add_argument("--nix-unsupported-only", action="store_true", help="Process only files that are not managed by Nix")
    args = parser.parse_args()

    repo_root = get_repo_root()
    home = Path.home()
    pairs = expand_map(repo_root, home, args.nix_unsupported_only)

    if args.unlink:
        unlink(pairs, home, args.dry_run)
    else:
        deploy(pairs, args.dry_run)


if __name__ == "__main__":
    main()
