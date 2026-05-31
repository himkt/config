# config

[![macOS](https://img.shields.io/github/actions/workflow/status/himkt/dotfiles/macos.yml?label=macOS&logo=apple)](https://github.com/himkt/dotfiles/actions/workflows/macos.yml)
[![NixOS](https://img.shields.io/github/actions/workflow/status/himkt/dotfiles/nixos.yml?label=NixOS&logo=nixos&logoColor=white)](https://github.com/himkt/dotfiles/actions/workflows/nixos.yml)

Unified Nix-based configuration for macOS (nix-darwin) and NixOS.

## Structure

```
dotfiles/
├── flake.nix          # Unified flake (NixOS + nix-darwin)
├── Makefile           # Build and link targets
├── bin/               # link.py — creates working-tree symlinks
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
4. Link dotfiles as working-tree symlinks:
   ```
   make link
   ```
5. Install Homebrew packages:
   ```
   make brew
   make brew-gui
   ```

### NixOS

1. Clone this repository to `~/dotfiles`
2. Apply the NixOS configuration:
   ```
   make switch
   ```
3. Link dotfiles as working-tree symlinks:
   ```
   make link
   ```

> **Dotfiles linking.** `make switch` manages packages and system settings only. Configuration files (git, mise, nvim, tmux, uv, ghostty, sheldon, zsh, and `~/.claude`) are linked separately by `make link`, which symlinks them directly to the working tree so edits take effect immediately without a rebuild.
>
> **Migrating an existing machine.** If these files were previously managed by Home Manager (symlinks into `/nix/store`), run `make switch` first — Home Manager removes the old store symlinks on activation — then `make link`. `link` is strict: it aborts if a destination already exists. Resolve any reported conflicts and re-run. Use `make unlink` to remove the symlinks.

## Makefile Targets

All Nix targets automatically detect the platform (macOS / NixOS) and run the appropriate command.

| Target | Description |
|--------|-------------|
| `build` | Build system configuration (dry run) |
| `switch` | Apply system + Home Manager configuration |
| `link` | Link dotfiles as working-tree symlinks (run after `switch`) |
| `unlink` | Remove the dotfile symlinks created by `link` |
| `update` | Update flake inputs |
| `gc` | Delete old generations (keep last 7) and run garbage collection |
| `brew-install` | Install Homebrew |
| `brew` | Install base Homebrew packages |
| `brew-gui` | Install GUI Homebrew packages |
| `brew-optional` | Install optional Homebrew packages |
| `brew-himkt` | Install personal Homebrew packages |
