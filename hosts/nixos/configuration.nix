# Edit this configuration file to define what should be installed on
# your system.  Help is available in the configuration.nix(5) man page
# and in the NixOS manual (accessible by running ‘nixos-help’).

{ config, pkgs, ... }:

{
  imports =
    [ # Include the results of the hardware scan.
      ./hardware-configuration.nix
      ../modules/keyd
    ];

  # Bootloader.
  boot.loader.systemd-boot.enable = true;
  boot.loader.efi.canTouchEfiVariables = true;

  boot.kernelPackages = pkgs.linuxPackages_latest;

  boot.initrd.luks.devices."luks-8e3f8068-90b0-4614-a514-98ae63db54ab".device = "/dev/disk/by-uuid/8e3f8068-90b0-4614-a514-98ae63db54ab";
  networking.hostName = "neptune"; # Define your hostname.
  # networking.wireless.enable = true;  # Enables wireless support via wpa_supplicant.

  # Configure network proxy if necessary
  # networking.proxy.default = "http://user:password@proxy:port/";
  # networking.proxy.noProxy = "127.0.0.1,localhost,internal.domain";

  # Enable networking
  networking.networkmanager.enable = true;

  # sops-nix secrets
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

  # DNS over TLS with NextDNS
  services.resolved = {
    enable = true;
    dnsovertls = "true";
    fallbackDns = [];
  };
  networking.networkmanager.dns = "systemd-resolved";

  # Set your time zone.
  time.timeZone = "Asia/Tokyo";

  # Select internationalisation properties.
  i18n.defaultLocale = "en_US.UTF-8";

  i18n.extraLocaleSettings = {
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

  # Enable the X11 windowing system.
  services.xserver.enable = true;

  # Enable the GNOME Desktop Environment.
  services.displayManager.gdm.enable = true;
  services.desktopManager.gnome.enable = true;

  # Configure keymap in X11
  services.xserver.xkb = {
    layout = "us";
    variant = "";
  };

  # Enable CUPS to print documents.
  services.printing.enable = true;

  # FIXME(himkt); fprint not working so well in some cases.
  #               when finger print reader is not available,
  #               the experience is not so good as macOS (waiting until timeout).
  #               this happens when I use computer in clamshell mode and
  #               keyboard without fingerprint reader.
  #
  # Fingerprint reader
  # services.fprintd = {
  #   enable = true;
  #   tod = {
  #     enable = true;
  #     driver = pkgs.libfprint-2-tod1-goodix;  # note; Goodix 27c6:658c
  #   };
  # };

  # Enable sound with pipewire.
  services.pulseaudio.enable = false;
  security.rtkit.enable = true;

  security.pam.services.gdm.enableGnomeKeyring = true;
  services.gnome.gnome-keyring.enable = true;

  services.pipewire = {
    enable = true;
    alsa.enable = true;
    alsa.support32Bit = true;
    pulse.enable = true;
    # If you want to use JACK applications, uncomment this
    #jack.enable = true;

    # use the example session manager (no others are packaged yet so this is enabled by default,
    # no need to redefine it in your config for now)
    #media-session.enable = true;
  };

  # Enable touchpad support (enabled default in most desktopManager).
  # services.xserver.libinput.enable = true;

  # Docker
  virtualisation.docker = {
    enable = true;
    enableOnBoot = false;
  };
  systemd.sockets.docker.wantedBy = pkgs.lib.mkForce [];

  # Define a user account. Don't forget to set a password with 'passwd'.
  users.users.himkt = {
    isNormalUser = true;
    description = "himkt";
    extraGroups = [ "networkmanager" "wheel" "docker" ];
    packages = with pkgs; [
    #  thunderbird
    ];
    shell = pkgs.zsh;
  };

  # Install firefox.
  programs.firefox.enable = true;
  programs.zsh.enable = true;
  programs.nix-ld.enable = true;
  programs.nix-ld.libraries = with pkgs; [
    glib
    libGL
    postgresql.lib
  ];

  # Allow unfree packages
  nixpkgs.config.allowUnfree = true;

  # List packages installed in system profile. To search, run:
  # $ nix search wget
  environment.systemPackages = with pkgs; [
  #  vim # Do not forget to add an editor to edit configuration.nix! The Nano editor is also installed by default.
  #  wget
  ];

  fonts.packages = with pkgs; [
    jetbrains-mono
    noto-fonts
    noto-fonts-color-emoji
    noto-fonts-cjk-sans
  ];

  # Some programs need SUID wrappers, can be configured further or are
  # started in user sessions.
  # programs.mtr.enable = true;
  # programs.gnupg.agent = {
  #   enable = true;
  #   enableSSHSupport = true;
  # };

  # List services that you want to enable:

  # Enable the OpenSSH daemon.
  # services.openssh.enable = true;

  # Open ports in the firewall.
  # networking.firewall.allowedTCPPorts = [ ... ];
  # networking.firewall.allowedUDPPorts = [ ... ];
  # Or disable the firewall altogether.
  # networking.firewall.enable = false;
  networking.firewall.trustedInterfaces = [ "docker0" "br-+" ];

  # This value determines the NixOS release from which the default
  # settings for stateful data, like file locations and database versions
  # on your system were taken. It‘s perfectly fine and recommended to leave
  # this value at the release version of the first install of this system.
  # Before changing this value read the documentation for this option
  # (e.g. man configuration.nix or on https://nixos.org/nixos/options.html).
  nix.settings.experimental-features = [ "nix-command" "flakes" ];

  system.stateVersion = "25.11"; # Did you read the comment?

}
