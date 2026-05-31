{ config, pkgs, lib, inputs, ... }:

let
  himkt_pkgs = import ./pkgs {
    inherit pkgs;
  };
in

{
  imports = [ ];

  home = {
    homeDirectory = "/Users/himkt";
    stateVersion  = "25.11";
    username      = "himkt";
  };

  programs = {
    home-manager.enable = true;
  };

  xdg = {
    enable     = true;
    configHome = "${config.home.homeDirectory}/.config";
    cacheHome  = "${config.home.homeDirectory}/.cache";
    dataHome   = "${config.home.homeDirectory}/.local/share";
  };
}
