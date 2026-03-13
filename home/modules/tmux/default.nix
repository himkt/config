{
  config,
  pkgs,
  lib,
  ...
}:

{
  home.packages = with pkgs; [
    tmux
  ];

  xdg.configFile."tmux/tmux.conf" = {
    source = ./files/tmux.conf;
  };
}
