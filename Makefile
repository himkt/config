UNAME := $(shell uname -s)

ifeq ($(UNAME),Darwin)
  NIX_BUILD_CMD := nix build .\#darwinConfigurations.macos.system
  NIX_SWITCH_CMD := sudo darwin-rebuild switch --flake .\#macos
else
  NIX_BUILD_CMD := nix build .\#nixosConfigurations.nixos.config.system.build.toplevel
  NIX_SWITCH_CMD := sudo nixos-rebuild switch --flake .\#nixos
endif

MISE_ENV := MISE_GLOBAL_CONFIG_FILE=$(CURDIR)/mise/config.toml

.PHONY: build switch update gc brew brew-base brew-gui brew-himkt bootstrap bootstrap-check

# mise bootstrap targets
bootstrap:
	$(MISE_ENV) mise bootstrap --yes

# CI-oriented: --force because runner images ship stock dotfiles
# (e.g. ~/.zshrc); never needed in the normal local flow.
bootstrap-check:
	$(MISE_ENV) mise bootstrap dotfiles apply --force
	$(MISE_ENV) mise bootstrap --dry-run --yes

# Nix targets (platform-aware)
build:
	$(NIX_BUILD_CMD)

switch:
	$(NIX_SWITCH_CMD)

update:
	nix flake update

gc:
	sudo nix-env --delete-generations +7 --profile /nix/var/nix/profiles/system
	sudo nix-collect-garbage -d

# Homebrew targets (macOS only)
brew:
	$(PWD)/brew/bin/setup.sh

brew-base:
	brew bundle --verbose --file=$(PWD)/brew/config.d/base/Brewfile

brew-gui:
	brew bundle --verbose --file=$(PWD)/brew/config.d/gui/Brewfile

brew-himkt:
	brew bundle --verbose --file=$(PWD)/brew/config.d/himkt/Brewfile
