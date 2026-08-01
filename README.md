# config

[![bootstrap](https://img.shields.io/github/actions/workflow/status/himkt/dotfiles/bootstrap.yml?label=bootstrap&logo=apple)](https://github.com/himkt/dotfiles/actions/workflows/bootstrap.yml)

macOS configuration managed with [mise](https://mise.jdx.dev/) bootstrap: dotfiles, macOS defaults, and versioned dev tools from a single `mise/config.toml`.

## Structure

```
dotfiles/
├── Makefile           # Bootstrap and Homebrew targets
├── bin/               # setup-touchid-sudo.sh — enables Touch ID for sudo
├── brew/              # Homebrew installer script and Brewfiles
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
2. Install mise:
   ```
   brew install mise
   ```
3. Clone this repository to `~/dotfiles`
4. Apply dotfiles and macOS defaults:
   ```
   make bootstrap
   ```
5. Enable Touch ID for sudo:
   ```
   make touchid-sudo
   ```
6. Install Homebrew packages:
   ```
   make brew-base
   make brew-gui
   ```

> **Dotfiles.** Configuration files (git, mise, nvim, tmux, uv, ghostty, herdr, sheldon, zsh, and `~/.claude`) are applied by `make bootstrap` via the `[dotfiles]` section of `mise/config.toml`, which symlinks them directly to the working tree so edits take effect immediately. Re-running is safe: entries already in their desired state are skipped. mise refuses to replace files it does not manage — resolve any reported conflicts manually, then re-run. Check state anytime with `mise bootstrap dotfiles status`.

## Makefile Targets

| Target | Description |
|--------|-------------|
| `bootstrap` | Apply mise bootstrap (dotfiles, macOS defaults) from `mise/config.toml` |
| `bootstrap-check` | CI check: dotfiles apply plus config-wide dry-run |
| `touchid-sudo` | Enable Touch ID for sudo (requires sudo; idempotent) |
| `brew` | Install Homebrew |
| `brew-base` | Install base Homebrew packages |
| `brew-gui` | Install GUI Homebrew packages |
| `brew-himkt` | Install personal Homebrew packages |
