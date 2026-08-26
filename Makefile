.PHONY: bootstrap bootstrap-check brew brew-bundle brew-bundle-check mise touchid-sudo

mise:
	curl https://mise.run | sh

brew:
	$(PWD)/bin/setup-homebrew.sh

brew-bundle:
	brew bundle --verbose --file=$(PWD)/brew/Brewfile

brew-bundle-check:
	HOMEBREW_BUNDLE_NO_UPGRADE=1 brew bundle check --verbose --file=$(PWD)/brew/Brewfile

up:
	mise up
	mise bootstrap --yes
	mise bootstrap packages upgrade --yes

touchid-sudo:
	$(PWD)/bin/setup-touchid-sudo.sh
