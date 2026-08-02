# config

[![bootstrap](https://img.shields.io/github/actions/workflow/status/himkt/config/bootstrap.yml?label=bootstrap&logo=apple)](https://github.com/himkt/config/actions/workflows/bootstrap.yml)

Linux and macOS configuration driven by [mise](https://mise.jdx.dev/) bootstrap.
A single `mise/config.toml` declares everything: dotfile symlinks, Homebrew packages, macOS defaults, and versioned dev tools.
Most top-level directories here are the source for one of those symlinks — see `[dotfiles]` for the mapping.

## Setup

```
make mise          # install mise
make bootstrap     # apply dotfiles, packages, and macOS defaults
make touchid-sudo  # enable Touch ID for sudo (optional, macOS only)
make brew          # install Homebrew (optional)
```
