# config

[![macOS](https://img.shields.io/github/actions/workflow/status/himkt/dotfiles/macos.yml?label=macOS&logo=apple)](https://github.com/himkt/dotfiles/actions/workflows/macos.yml)
[![NixOS](https://img.shields.io/github/actions/workflow/status/himkt/dotfiles/nixos.yml?label=NixOS&logo=nixos&logoColor=white)](https://github.com/himkt/dotfiles/actions/workflows/nixos.yml)

Unified Nix-based configuration for macOS (nix-darwin) and NixOS.

## Structure

```
dotfiles/
├── flake.nix          # Unified flake (NixOS + nix-darwin)
├── Makefile           # Build and bootstrap targets
├── nix/               # All Nix-managed system + Home Manager config
│   ├── hosts/
│   │   ├── nixos/     # NixOS system configuration
│   │   └── macos/     # nix-darwin system configuration
│   ├── home/
│   │   ├── nixos.nix  # NixOS Home Manager entry point
│   │   ├── macos.nix  # macOS Home Manager entry point
│   │   └── modules/   # Shared and platform-specific modules
│   └── secrets/       # sops-nix encrypted secrets
├── brew/              # Homebrew Brewfiles (macOS)
├── claude/            # dotfile source → ~/.claude
├── ghostty/           # dotfile source → ~/.config/ghostty
├── git/               # dotfile source → ~/.config/git
├── herdr/             # dotfile source → ~/.config/herdr
├── mise/              # dotfile source → ~/.config/mise
├── nvim/              # dotfile source → ~/.config/nvim
├── sheldon/           # dotfile source → ~/.config/sheldon
├── tmux/              # dotfile source → ~/.config/tmux
├── uv/                # dotfile source → ~/.config/uv
└── zsh/               # dotfile source → ~/.zshrc (zsh/zshrc)
```

## Setup

### macOS

1. Install [Nix](https://nixos.org/download/)
2. Clone this repository to `~/dotfiles`
3. Apply the nix-darwin configuration:
   ```
   make switch
   ```
4. Install Homebrew (`make brew`) and mise (`brew install mise`), then apply dotfiles and macOS defaults:
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

### NixOS

1. Clone this repository to `~/dotfiles`
2. Apply the NixOS configuration:
   ```
   make switch
   ```

> **Dotfiles.** `make switch` manages packages and system settings only. Configuration files (git, mise, nvim, tmux, uv, ghostty, herdr, sheldon, zsh, and `~/.claude`) are applied by `make bootstrap` via the `[dotfiles]` section of `mise/config.toml`, which symlinks them directly to the working tree so edits take effect immediately without a rebuild. Re-running is safe: entries already in their desired state are skipped. mise refuses to replace files it does not manage — resolve any reported conflicts manually, then re-run. Check state anytime with `mise bootstrap dotfiles status`.

## Makefile Targets

All Nix targets automatically detect the platform (macOS / NixOS) and run the appropriate command.

| Target | Description |
|--------|-------------|
| `build` | Build system configuration (dry run) |
| `switch` | Apply system + Home Manager configuration |
| `bootstrap` | Apply mise bootstrap (dotfiles, macOS defaults) from `mise/config.toml` |
| `bootstrap-check` | CI check: dotfiles apply plus config-wide dry-run |
| `touchid-sudo` | Enable Touch ID for sudo (requires sudo; idempotent) |
| `update` | Update flake inputs |
| `gc` | Delete old generations (keep last 7) and run garbage collection |
| `brew` | Install Homebrew |
| `brew-base` | Install base Homebrew packages |
| `brew-gui` | Install GUI Homebrew packages |
| `brew-himkt` | Install personal Homebrew packages |
