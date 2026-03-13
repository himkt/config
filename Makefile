UNAME := $(shell uname -s)

ifeq ($(UNAME),Darwin)
  NIX_BUILD_CMD := nix build .\#darwinConfigurations.macos.system
  NIX_SWITCH_CMD := sudo darwin-rebuild switch --flake .\#macos
else
  NIX_BUILD_CMD := nix build .\#nixosConfigurations.nixos.config.system.build.toplevel
  NIX_SWITCH_CMD := sudo nixos-rebuild switch --flake .\#nixos
endif

.PHONY: build switch update gc brew-install brew brew-gui brew-optional brew-himkt simple-deploy simple-unlink

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
brew-install:
	$(PWD)/brew/bin/setup.sh

brew:
	brew bundle --verbose --file=$(PWD)/brew/config.d/base/Brewfile

brew-gui:
	brew bundle --verbose --file=$(PWD)/brew/config.d/gui/Brewfile

brew-optional:
	brew bundle --verbose --file=$(PWD)/brew/config.d/optional/Brewfile

brew-himkt:
	brew bundle --verbose --file=$(PWD)/brew/config.d/himkt/Brewfile

simple-deploy:
	python3 bin/simple-deploy.py --dry-run
	python3 bin/simple-deploy.py

simple-unlink:
	python3 bin/simple-deploy.py --unlink
