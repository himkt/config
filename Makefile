.PHONY: bootstrap bootstrap-check brew brew-bundle brew-bundle-check mise touchid-sudo

mise:
	curl https://mise.run | sh

brew:
	$(PWD)/bin/setup-homebrew.sh

brew-bundle:
	brew bundle --verbose --file=$(PWD)/brew/Brewfile

brew-bundle-check:
	HOMEBREW_BUNDLE_NO_UPGRADE=1 brew bundle check --verbose --file=$(PWD)/brew/Brewfile

bootstrap:
	mise bootstrap --yes

# CI-oriented: --force because runner images ship stock dotfiles
# (e.g. ~/.zshrc); never needed in the normal local flow.
bootstrap-check:
	mise bootstrap dotfiles apply --force
	mise bootstrap --dry-run --yes

touchid-sudo:
	$(PWD)/bin/setup-touchid-sudo.sh
