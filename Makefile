MISE_ENV := MISE_GLOBAL_CONFIG_FILE=$(CURDIR)/mise/config.toml

.PHONY: brew brew-base brew-gui brew-himkt bootstrap bootstrap-check touchid-sudo

# mise bootstrap targets
bootstrap:
	$(MISE_ENV) mise bootstrap --yes

# CI-oriented: --force because runner images ship stock dotfiles
# (e.g. ~/.zshrc); never needed in the normal local flow.
bootstrap-check:
	$(MISE_ENV) mise bootstrap dotfiles apply --force
	$(MISE_ENV) mise bootstrap --dry-run --yes

# Requires sudo; runs once per machine (idempotent).
touchid-sudo:
	$(PWD)/bin/setup-touchid-sudo.sh

# Homebrew targets
brew:
	$(PWD)/brew/bin/setup.sh

brew-base:
	brew bundle --verbose --file=$(PWD)/brew/config.d/base/Brewfile

brew-gui:
	brew bundle --verbose --file=$(PWD)/brew/config.d/gui/Brewfile

brew-himkt:
	brew bundle --verbose --file=$(PWD)/brew/config.d/himkt/Brewfile
