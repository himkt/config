{
  description = "NixOS and nix-darwin configuration for himkt";

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/nixos-25.11";
    nixpkgs-unstable.url = "github:nixos/nixpkgs/nixos-unstable";

    home-manager = {
      url = "github:nix-community/home-manager/release-25.11";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    nix-darwin = {
      url = "github:LnL7/nix-darwin/nix-darwin-25.11";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    sops-nix = {
      url = "github:Mic92/sops-nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs =
    {
      self,
      nixpkgs,
      home-manager,
      nix-darwin,
      ...
    }@inputs:
    {
      # NixOS configuration
      nixosConfigurations.nixos = nixpkgs.lib.nixosSystem {
        system = "x86_64-linux";
        specialArgs = { inherit inputs; username = "himkt"; };
        modules = [
          ./hosts/nixos/configuration.nix
          inputs.sops-nix.nixosModules.sops
          home-manager.nixosModules.home-manager
          {
            home-manager.useGlobalPkgs = true;
            home-manager.useUserPackages = true;
            home-manager.users.himkt = import ./home/nixos.nix;
            home-manager.extraSpecialArgs = {
              inherit inputs;
              username = "himkt";
            };
          }
        ];
      };

      # nix-darwin configuration
      darwinConfigurations.macos = nix-darwin.lib.darwinSystem {
        system = "aarch64-darwin";
        specialArgs = { inherit inputs; username = "himkt"; };
        modules = [
          ./hosts/macos/darwin-configuration.nix
          home-manager.darwinModules.home-manager
          {
            home-manager.useGlobalPkgs = true;
            home-manager.useUserPackages = true;
            home-manager.users.himkt = import ./home/macos.nix;
            home-manager.extraSpecialArgs = {
              inherit inputs;
              username = "himkt";
            };
          }
        ];
      };
    };
}
