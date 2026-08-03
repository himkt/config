.PHONY: bootstrap bootstrap-check brew brew-install brew-bundle mise touchid-sudo

mise:
	curl https://mise.run | sh

brew:
	$(PWD)/bin/setup-homebrew.sh

bootstrap:
	mise bootstrap --yes

# CI-oriented: --force because runner images ship stock dotfiles
# (e.g. ~/.zshrc); never needed in the normal local flow.
bootstrap-check:
	mise bootstrap dotfiles apply --force
	mise bootstrap --dry-run --yes

touchid-sudo:
	$(PWD)/bin/setup-touchid-sudo.sh
