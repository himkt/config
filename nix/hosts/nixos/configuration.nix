{ config, pkgs, ... }:

{
  imports = [
    ./hardware-configuration.nix
  ];

  boot = {
    loader = {
      systemd-boot.enable      = true;
      efi.canTouchEfiVariables = true;
    };
    kernelPackages = pkgs.linuxPackages_6_18;
    initrd.luks.devices."luks-8e3f8068-90b0-4614-a514-98ae63db54ab".device = "/dev/disk/by-uuid/8e3f8068-90b0-4614-a514-98ae63db54ab";
  };

  fonts = {
    packages = with pkgs; [
      jetbrains-mono
      noto-fonts
      noto-fonts-color-emoji
      noto-fonts-cjk-sans
    ];
  };

  i18n = {
    defaultLocale       = "en_US.UTF-8";
    extraLocaleSettings = {
      LC_ADDRESS = "ja_JP.UTF-8";
      LC_IDENTIFICATION = "ja_JP.UTF-8";
      LC_MEASUREMENT = "ja_JP.UTF-8";
      LC_MONETARY = "ja_JP.UTF-8";
      LC_NAME = "ja_JP.UTF-8";
      LC_NUMERIC = "ja_JP.UTF-8";
      LC_PAPER = "ja_JP.UTF-8";
      LC_TELEPHONE = "ja_JP.UTF-8";
      LC_TIME = "ja_JP.UTF-8";
    };
  };

  networking = {
    firewall = {
      trustedInterfaces = [ "docker0" "br-+" ];
    };
    hostName = "neptune";
    networkmanager = {
      enable = true;
      dns    = "systemd-resolved";
    };
  };

  nix = {
    settings.experimental-features = [ "nix-command" "flakes" ];
  };

  nixpkgs = {
    config.allowUnfree = true;
  };

  programs = {
    nix-ld = {
      enable    = true;
      libraries = with pkgs; [
        glib
        libGL
        postgresql.lib
      ];
    };
    zsh.enable = true;
    ssh.startAgent = true;
  };

  security = {
    pam.services.gdm.enableGnomeKeyring = true;
    rtkit.enable = true;
  };

  services = {
    # FIXME(himkt); fprint not working so well in some cases.
    #               when finger print reader is not available,
    #               the experience is not so good as macOS (waiting until timeout).
    #               this happens when I use computer in clamshell mode and
    #               keyboard without fingerprint reader.
    #
    # Fingerprint reader
    # fprintd = {
    #   enable = true;
    #   tod = {
    #     enable = true;
    #     driver = pkgs.libfprint-2-tod1-goodix;  # note; Goodix 27c6:658c
    #   };
    # };
    desktopManager = {
      gnome.enable = true;
    };

    displayManager = {
      gdm.enable = true;
    };

    gnome = {
      gnome-keyring.enable = true;
      gcr-ssh-agent.enable = false;
    };

    keyd = {
      enable = true;
      keyboards = {
        default = {
          settings = {
            main = {
              capslock = "leftcontrol";
            };
            control = {
              left = "home";
              right = "end";
              up = "C-home";
              down = "C-end";
            };
            "meta+control" = {
              left = "M-pageup";
              right = "M-pagedown";
            };
            meta = {
              q = "A-f4";
            };
          };
        };
      };
    };

    pipewire = {
      enable            = true;
      alsa.enable       = true;
      alsa.support32Bit = true;
      pulse.enable      = true;
    };

    printing = {
      enable = true;
    };

    pulseaudio = {
      enable = false;
    };

    resolved = {
      enable      = true;
      dnsovertls  = "true";
      fallbackDns = [];
    };

    xserver = {
      enable = true;
      xkb    = {
        layout  = "us";
        variant = "";
      };
    };
  };

  sops = {
    defaultSopsFile = ../../secrets/secrets.yaml;
    age.keyFile = "/var/lib/sops-nix/key.txt";
    secrets.nextdns_id = {};
    secrets.dns_server_ipv4_0 = {};
    secrets.dns_server_ipv4_1 = {};
    secrets.dns_server_ipv6_0 = {};
    secrets.dns_server_ipv6_1 = {};
    templates."99-nextdns.conf" = {
      content = ''
        [Resolve]
        DNS=${config.sops.placeholder.dns_server_ipv4_0}#${config.sops.placeholder.nextdns_id}.dns.nextdns.io
        DNS=${config.sops.placeholder.dns_server_ipv6_0}#${config.sops.placeholder.nextdns_id}.dns.nextdns.io
        DNS=${config.sops.placeholder.dns_server_ipv4_1}#${config.sops.placeholder.nextdns_id}.dns.nextdns.io
        DNS=${config.sops.placeholder.dns_server_ipv6_1}#${config.sops.placeholder.nextdns_id}.dns.nextdns.io
      '';
      path = "/etc/systemd/resolved.conf.d/99-nextdns.conf";
      mode = "0644";
      restartUnits = [ "systemd-resolved.service" ];
    };
  };

  system = {
    stateVersion = "26.05";
  };

  time = {
    timeZone = "Asia/Tokyo";
  };

  virtualisation = {
    docker = {
      enable = true;
      enableOnBoot = false;
    };
  };

  users = {
    users.himkt = {
      isNormalUser = true;
      description  = "himkt";
      extraGroups  = [ "networkmanager" "wheel" "docker" ];
      shell        = pkgs.zsh;
    };
  };
}
