{ config, lib, pkgs, ... }:

let
  himkt_pkgs = import ./pkgs {
    inherit pkgs;
  };

in
{
  home = {
    homeDirectory = "/Users/himkt";
    stateVersion  = "25.11";
    username      = "himkt";

    packages = [
      # Custom packages
      himkt_pkgs.pathfinder
    ];
  };

  programs = {
    home-manager = {
      enable = true;
    };
  };

  xdg = {
    enable     = true;
    configHome = "${config.home.homeDirectory}/.config";
    cacheHome  = "${config.home.homeDirectory}/.cache";
    dataHome   = "${config.home.homeDirectory}/.local/share";
  };
}
