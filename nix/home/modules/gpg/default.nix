{
  pkgs,
  config,
  ...
}:

{
  programs.gpg = {
    enable = true;
    package = pkgs.gnupg;
    homedir = "${config.xdg.dataHome}/gnupg";

    mutableKeys = true;
    mutableTrust = true;
  };
}
