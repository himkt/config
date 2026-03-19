{ config, pkgs, lib, inputs, ... }:

let
  himkt_pkgs = import ./pkgs {
    inherit pkgs;
  };
in

{
  imports = [
    ./modules/ghostty
    ./modules/git
    ./modules/mise
    ./modules/nvim
    ./modules/sheldon
    ./modules/tmux
    ./modules/uv
    ./modules/zsh
  ];

  home.username = "himkt";
  home.homeDirectory = "/Users/himkt";
  home.stateVersion = "25.11";

  xdg = {
    enable = true;
    configHome = "${config.home.homeDirectory}/.config";
    cacheHome = "${config.home.homeDirectory}/.cache";
    dataHome = "${config.home.homeDirectory}/.local/share";
  };

  home.packages = with pkgs; [
    # CLI
    btop
    python3
    rustup
    tree

    # Custom packages
    himkt_pkgs.pathfinder
  ];

  programs.home-manager.enable = true;
}
