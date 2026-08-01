# config

[![bootstrap](https://img.shields.io/github/actions/workflow/status/himkt/dotfiles/bootstrap.yml?label=bootstrap&logo=apple)](https://github.com/himkt/dotfiles/actions/workflows/bootstrap.yml)

macOS configuration managed with [mise](https://mise.jdx.dev/) bootstrap: dotfiles, Homebrew packages, macOS defaults, and versioned dev tools from a single `mise/config.toml`.

## Structure

```
dotfiles/
├── Makefile           # Bootstrap and Homebrew targets
├── bin/               # setup-touchid-sudo.sh — enables Touch ID for sudo
├── brew/              # Homebrew installer script and Brewfile (mise)
├── claude/            # dotfile source → ~/.claude
├── ghostty/           # dotfile source → ~/.config/ghostty
├── git/               # dotfile source → ~/.config/git
├── herdr/             # dotfile source → ~/.config/herdr
├── mise/              # dotfile source → ~/.config/mise (also the bootstrap config)
├── nvim/              # dotfile source → ~/.config/nvim
├── sheldon/           # dotfile source → ~/.config/sheldon
├── tmux/              # dotfile source → ~/.config/tmux
├── uv/                # dotfile source → ~/.config/uv
└── zsh/               # dotfile source → ~/.zshrc (zsh/zshrc)
```

## Setup

1. Install Homebrew:
   ```
   /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
   ```
2. Clone this repository to `~/dotfiles`
3. Install mise:
   ```
   make brew-bundle
   ```
4. Apply dotfiles, packages, and macOS defaults:
   ```
   make bootstrap
   ```
5. Enable Touch ID for sudo:
   ```
   make touchid-sudo
   ```

> **Dotfiles.** Configuration files (git, mise, nvim, tmux, uv, ghostty, herdr, sheldon, zsh, and `~/.claude`) are applied by `make bootstrap` via the `[dotfiles]` section of `mise/config.toml`, which symlinks them directly to the working tree so edits take effect immediately. Re-running is safe: entries already in their desired state are skipped. mise refuses to replace files it does not manage — resolve any reported conflicts manually, then re-run. Check state anytime with `mise bootstrap dotfiles status`.
>
> **Packages.** Homebrew formulas and casks are declared in `[bootstrap.packages]` of `mise/config.toml` and installed by `make bootstrap` — mise fetches Homebrew API metadata itself and never shells out to `brew`, so formulas use canonical API names (e.g. `python@3.13`). `himkt/tap` packages resolve the same way via the tap's published API metadata. Check state anytime with `mise bootstrap packages status`.
>
> **Removing packages.** NEVER run `mise bootstrap packages prune` here: it removes every linked formula outside the config's dependency closure — including brew-owned mise itself — with no keep-list. Removal is manual: after deleting the config entry, run `brew uninstall <formula>` for brew-installed formulas, and delete the installed artifacts (e.g. the app bundle in `/Applications`) for mise-installed casks.

## Makefile Targets

| Target | Description |
|--------|-------------|
| `bootstrap` | Apply mise bootstrap (dotfiles, packages, macOS defaults) from `mise/config.toml` |
| `bootstrap-check` | CI check: dotfiles apply plus config-wide dry-run |
| `touchid-sudo` | Enable Touch ID for sudo (requires sudo; idempotent) |
| `brew-install` | Install Homebrew |
| `brew-bundle` | Install brew-owned packages (mise) from `brew/Brewfile` |
