{ config, pkgs, lib, inputs, ... }:

let
  unstable = import inputs.nixpkgs-unstable {
    system = pkgs.stdenv.hostPlatform.system;
    config.allowUnfree = true;
  };
  himkt_pkgs = import ./pkgs {
    inherit pkgs;
  };
in

{
  imports = [
    ./modules/claude-code
    ./modules/gcc
    ./modules/ghostty
    ./modules/git
    ./modules/java
    ./modules/mise
    ./modules/nvim
    ./modules/sheldon
    ./modules/tmux
    ./modules/uv
    ./modules/zsh
    # NixOS specific
    ./modules/fcitx5
    ./modules/gpg
  ];

  home.username = "himkt";
  home.homeDirectory = "/home/himkt";
  home.stateVersion = "25.11";

  xdg = {
    enable = true;
    configHome = "${config.home.homeDirectory}/.config";
    cacheHome = "${config.home.homeDirectory}/.cache";
    dataHome = "${config.home.homeDirectory}/.local/share";
  };

  home.packages = with pkgs; [
    # GUI
    google-chrome
    inkscape
    insomnia
    slack
    unstable._1password-gui
    unstable.vscode

    # CLI
    btop
    file
    gnumake
    postgresql
    python3
    rustup
    tree

    # Custom packages
    himkt_pkgs.pathfinder
  ];

  home.file = {
    # Chrome with touchpad swipe gesture support
    ".local/share/applications/google-chrome.desktop".text = ''
      [Desktop Entry]
      Version=1.0
      Name=Google Chrome
      GenericName=Web Browser
      Comment=Access the Internet
      Exec=google-chrome-stable --enable-features=TouchpadOverscrollHistoryNavigation %U
      StartupNotify=true
      Terminal=false
      Icon=google-chrome
      Type=Application
      Categories=Network;WebBrowser;
      MimeType=text/html;text/xml;application/xhtml+xml;x-scheme-handler/http;x-scheme-handler/https;
    '';

    # Hide duplicate Chrome entry
    ".local/share/applications/com.google.Chrome.desktop".text = ''
      [Desktop Entry]
      NoDisplay=true
    '';

    # Ghostty with fcitx5 workaround
    ".local/share/applications/com.mitchellh.ghostty.desktop".text = ''
      [Desktop Entry]
      Version=1.0
      Name=Ghostty
      GenericName=Terminal
      Comment=A terminal emulator
      Exec=env GTK_IM_MODULE= ghostty
      StartupNotify=true
      Terminal=false
      Icon=com.mitchellh.ghostty
      Type=Application
      Categories=System;TerminalEmulator;
    '';

    # VSCode with Wayland support
    ".local/share/applications/code.desktop".text = ''
      [Desktop Entry]
      Version=1.0
      Name=Visual Studio Code
      GenericName=Text Editor
      Comment=Code Editing. Redefined.
      Exec=code --ozone-platform=wayland %F
      StartupNotify=true
      Terminal=false
      Icon=vscode
      Type=Application
      Categories=Development;IDE;TextEditor;
      MimeType=text/plain;inode/directory;
    '';
  };

  home.sessionVariables = {
    EDITOR = "nvim";
    SSL_CERT_FILE = "/etc/ssl/certs/ca-certificates.crt";
    GTK_IM_MODULE = "fcitx";
    QT_IM_MODULE = "fcitx";
    XMODIFIERS = "@im=fcitx";
    GLFW_IM_MODULE = "ibus";
    ELECTRON_OZONE_PLATFORM_HINT = "auto";
    PLAYWRIGHT_MCP_EXECUTABLE_PATH = "/etc/profiles/per-user/himkt/bin/google-chrome-stable";
  };

  dconf.settings = {
    "org/gnome/mutter" = {
      experimental-features = [ "scale-monitor-framebuffer" ];
    };
    "org/gnome/desktop/peripherals/touchpad" = {
      tap-to-click = false;
      natural-scroll = true;
      speed = 0.0;
    };
    "org/gnome/desktop/peripherals/mouse" = {
      speed = -1.0;
      natural-scroll = true;
    };
    "org/gnome/desktop/interface" = {
      show-battery-percentage = true;
    };
  };

  fonts.fontconfig = {
    enable = true;
    defaultFonts = {
      monospace = [ "JetBrains Mono" "Noto Sans Mono CJK JP" ];
      sansSerif = [ "Noto Sans CJK JP" ];
      serif = [ "Noto Serif CJK JP" ];
      emoji = [ "Noto Color Emoji" ];
    };
  };

  # NixOS-specific platform overrides
  programs.zsh.shellAliases = {
    open = "xdg-open";
  };
  programs.home-manager.enable = true;
}
