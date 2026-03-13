{ pkgs, inputs, ... }:
let
  unstable = import inputs.nixpkgs-unstable {
    system = pkgs.stdenv.hostPlatform.system;
  };
in
{
  home.packages = [ unstable.mise ];
  xdg.configFile."mise/config.toml" = { source = ./files/config.toml; };
}
