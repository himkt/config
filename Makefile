.PHONY: all brew-up dotfiles krew-up mise mise-up touchid-sudo up

all: mise brew-up dotfiles krew-up mise-up

brew-up:
	mise bootstrap packages apply --yes
	mise bootstrap packages upgrade --yes

dotfiles:
	mise bootstrap dotfiles apply --yes

krew-up:
	kubectl krew install < krew/plugins

mise:
	curl https://mise.run | sh

mise-up:
	mise up

touchid-sudo:
	$(PWD)/bin/setup-touchid-sudo.sh

up: brew-up krew-up mise-up
