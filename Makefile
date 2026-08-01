MISE_ENV := MISE_GLOBAL_CONFIG_FILE=$(CURDIR)/mise/config.toml

.PHONY: brew-install brew-bundle bootstrap bootstrap-check touchid-sudo

bootstrap:
	$(MISE_ENV) mise bootstrap --yes

# CI-oriented: --force because runner images ship stock dotfiles
# (e.g. ~/.zshrc); never needed in the normal local flow.
bootstrap-check:
	$(MISE_ENV) mise bootstrap dotfiles apply --force
	$(MISE_ENV) mise bootstrap --dry-run --yes

touchid-sudo:
	$(PWD)/bin/setup-touchid-sudo.sh

brew-install:
	$(PWD)/brew/bin/setup.sh

brew-bundle:
	brew bundle --verbose --file=$(PWD)/brew/Brewfile
