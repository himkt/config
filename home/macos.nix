{ config, pkgs, lib, inputs, ... }:

let
  himkt_pkgs = import ./pkgs {
    inherit pkgs;
  };
in

{
  imports = [
    ./modules/claude-code
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

  home.sessionVariables = {
    EDITOR = "nvim";
  };

  # macOS-specific platform overrides
  programs.git.settings.credential."https://github.com".helper =
    lib.mkForce "!/opt/homebrew/bin/gh auth git-credential";

  programs.tmux.extraConfig = lib.mkAfter ''
    # macOS clipboard integration
    bind-key -T copy-mode-vi y     send -X copy-selection-and-cancel\; run "tmux save -|pbcopy"
    bind-key -T copy-mode-vi Enter send -X copy-selection-and-cancel\; run "tmux save -|pbcopy"
  '';

  programs.mise.globalConfig = {
    tools = {
      gcloud = "latest";
    };
    settings = {
      idiomatic_version_file_enable_tools = [];
    };
  };

  programs.home-manager.enable = true;
}
