# config

[![bootstrap](https://img.shields.io/github/actions/workflow/status/himkt/config/bootstrap.yml?label=bootstrap&logo=apple)](https://github.com/himkt/config/actions/workflows/bootstrap.yml)

Linux and macOS configuration driven by [mise](https://mise.jdx.dev/) bootstrap.
A single `mise/config.toml` declares dotfile installation, Homebrew packages, macOS defaults, and versioned dev tools.
Agent configuration, the command policy, and validator helpers use explicit copies so repository edits take effect after a reviewed installation. Other dotfiles use their configured mapping modes; see `[dotfiles]` for each source and target.

## Setup

```
make mise          # install mise
make bootstrap     # apply dotfiles, packages, and macOS defaults
make touchid-sudo  # enable Touch ID for sudo (optional, macOS only)
make brew          # install Homebrew (optional)
```

Review the [command policy and installation sequence](himkt/README.md) before applying agent configuration. Client acceptance is required before enabling the shared hook in a working installation.
