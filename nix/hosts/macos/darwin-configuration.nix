{ pkgs, ... }:

{
  # TODO: Remove once NixOS/nix#15638 is released.
  # https://github.com/NixOS/nixpkgs/issues/511265
  nixpkgs.overlays = [
    (final: prev: {
      python3Packages = prev.python3Packages.overrideScope (pfinal: pprev: {
        ffmpeg-python = pprev.ffmpeg-python.overridePythonAttrs {
          doCheck = false;
        };
      });
    })
  ];

  fonts = {
    packages = with pkgs; [
      jetbrains-mono
      noto-fonts-cjk-sans
    ];
  };

  nix = {
    settings.experimental-features = [ "nix-command" "flakes" ];
  };

  security = {
    pam.services.sudo_local.touchIdAuth = true;
  };

  system = {
    defaults = {
      dock = {
        orientation = "left";
        autohide = true;
      };
      trackpad.Clicking = true;
      NSGlobalDomain = {
        KeyRepeat = 2;
        InitialKeyRepeat = 20;
        ApplePressAndHoldEnabled = false;
        "com.apple.keyboard.fnState" = false;
      };
    };
    primaryUser = "himkt";
    # Note: verify this value before first activation.
    # See https://daiderd.com/nix-darwin/manual/ for stateVersion documentation.
    stateVersion = 5;
  };

  users = {
    users.himkt = {
      home = "/Users/himkt";
    };
  };
}
