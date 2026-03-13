{ pkgs, inputs, config, ... }:
let
  unstable = import inputs.nixpkgs-unstable {
    system = pkgs.stdenv.hostPlatform.system;
  };
in
{
  home.packages = [ unstable.mise ];
  home.sessionPath = [ "${config.xdg.dataHome}/mise/shims" ];
  xdg.configFile."mise/config.toml" = { source = ./files/config.toml; };
}
