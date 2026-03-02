# config

[![macOS](https://img.shields.io/github/actions/workflow/status/himkt/dotfiles/macos.yml?label=macOS&logo=apple)](https://github.com/himkt/dotfiles/actions/workflows/macos.yml)
[![NixOS](https://img.shields.io/github/actions/workflow/status/himkt/dotfiles/nixos.yml?label=NixOS&logo=nixos&logoColor=white)](https://github.com/himkt/dotfiles/actions/workflows/nixos.yml)

> [!IMPORTANT]
> People who are interested in Claude Code config, please visit [modules/claude-code](./home/modules/claude-code/files).

Unified Nix-based configuration for macOS (nix-darwin) and NixOS.

## Structure

```
dotfiles/
├── flake.nix          # Unified flake (NixOS + nix-darwin)
├── Makefile           # Build and setup targets
├── hosts/
│   ├── nixos/         # NixOS system configuration
│   └── macos/         # nix-darwin system configuration
├── home/
│   ├── nixos.nix      # NixOS Home Manager entry point
│   ├── macos.nix      # macOS Home Manager entry point
│   └── modules/       # Shared and platform-specific modules
├── brew/              # Homebrew Brewfiles (macOS)
└── secrets/           # sops-nix encrypted secrets
```

## Setup

### macOS

1. Install [Nix](https://nixos.org/download/)
2. Clone this repository to `~/dotfiles`
3. Apply the nix-darwin configuration:
   ```
   make switch
   ```
4. Install Homebrew packages:
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

## Makefile Targets

All Nix targets automatically detect the platform (macOS / NixOS) and run the appropriate command.

| Target | Description |
|--------|-------------|
| `build` | Build system configuration (dry run) |
| `switch` | Apply system + Home Manager configuration |
| `update` | Update flake inputs |
| `gc` | Delete old generations (keep last 7) and run garbage collection |
| `brew-install` | Install Homebrew |
| `brew` | Install base Homebrew packages |
| `brew-gui` | Install GUI Homebrew packages |
| `brew-optional` | Install optional Homebrew packages |
| `brew-himkt` | Install personal Homebrew packages |
