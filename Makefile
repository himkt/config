.PHONY: all brew-up dotfiles krew-up mise mise-up touchid-sudo

all: mise brew-up dotfiles krew-up mise-up

brew-up:
	mise bootstrap packages apply --yes
	mise bootstrap packages upgrade --yes

dotfiles:
	mise bootstrap dotfiles apply --yes

mise:
	curl https://mise.run | sh

mise-up:
	mise up

krew-up:
	kubectl krew install < krew/plugins

touchid-sudo:
	$(PWD)/bin/setup-touchid-sudo.sh
