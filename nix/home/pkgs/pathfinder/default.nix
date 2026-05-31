{
  lib,
  stdenv,
  fetchurl,
  autoPatchelfHook,
}:

let
  sources = {
    x86_64-linux = {
      url = "https://github.com/himkt/pathfinder/releases/download/v0.1.0/pathfinder-x86_64-unknown-linux-gnu.tar.gz";
      sha256 = "18bpvh651i1nk4agkxqqaax22y0fa3nwpfhhanlprzprq08cdvdk";
    };
    aarch64-darwin = {
      url = "https://github.com/himkt/pathfinder/releases/download/v0.1.0/pathfinder-aarch64-apple-darwin.tar.gz";
      sha256 = "1q50ipvfg9gy1s86j5i8393xyyfjqjif3i89sxhbyhxm8kvhl0gg";
    };
  };
in

stdenv.mkDerivation rec {
  pname = "pathfinder";
  version = "0.1.0";

  src = fetchurl sources.${stdenv.hostPlatform.system};

  nativeBuildInputs = lib.optionals stdenv.hostPlatform.isLinux [ autoPatchelfHook ];
  buildInputs = lib.optionals stdenv.hostPlatform.isLinux [ stdenv.cc.cc.lib ];

  sourceRoot = ".";

  installPhase = ''
    install -Dm755 pathfinder $out/bin/pathfinder
  '';

  meta = with lib; {
    description = "MCP client for jumping to definitions using LSP server";
    homepage = "https://github.com/himkt/pathfinder";
    license = licenses.mit;
    platforms = [ "x86_64-linux" "aarch64-darwin" ];
  };
}
