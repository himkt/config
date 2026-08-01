# config

[![bootstrap](https://img.shields.io/github/actions/workflow/status/himkt/dotfiles/bootstrap.yml?label=bootstrap&logo=apple)](https://github.com/himkt/dotfiles/actions/workflows/bootstrap.yml)

macOS configuration managed with [mise](https://mise.jdx.dev/) bootstrap: dotfiles, Homebrew packages, macOS defaults, and versioned dev tools from a single `mise/config.toml`.

## Structure

```
dotfiles/
├── Makefile           # Bootstrap and Homebrew targets
├── bash/              # dotfile source → ~/.bashrc (bash/bashrc)
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

1. Clone this repository to `~/dotfiles`
2. Install Homebrew:
   ```
   make brew-install
   ```
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

> **Packages.** mise fetches Homebrew API metadata itself and never shells out to `brew`, so formulas use canonical API names — `python@3.13`, not `python3`. Third-party taps must publish that metadata and be registered in `[bootstrap.brew.taps]`.
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
