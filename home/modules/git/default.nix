{
  config,
  pkgs,
  lib,
  ...
}:

{
  home.packages = with pkgs; [
    git
    git-lfs
  ];

  xdg.configFile."git/config" = {
    source = ./files/config;
  };

  xdg.configFile."git/ignore" = {
    source = ./files/ignore;
  };
}
