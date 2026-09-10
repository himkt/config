.PHONY: bootstrap bootstrap-check brew brew-bundle brew-bundle-check mise touchid-sudo

mise:
	curl https://mise.run | sh

krew-bundle:
	cat $(PWD)/krew/plugins | xargs kubectl krew install

up:
	mise up
	mise bootstrap dotfiles--yes

brew-up:
	mise bootstrap packages upgrade --yes

touchid-sudo:
	$(PWD)/bin/setup-touchid-sudo.sh
