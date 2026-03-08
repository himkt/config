{
  pkgs,
  inputs,
  ...
}:

let
  unstable = import inputs.nixpkgs-unstable {
    system = pkgs.stdenv.hostPlatform.system;
  };
in

{
  programs.mise = {
    enable = true;
    package = unstable.mise;
    enableZshIntegration = true;

    globalConfig = {
      tools = {
        "aqua:ahmetb/kubectx" = "latest";
        "aqua:anthropics/claude-code" = "latest";
        # FIXME(himkt): btop does not release binaries for macOS
        # "aqua:aristocratos/btop" = "latest";
        "aqua:bazelbuild/bazelisk" = "latest";
        "aqua:cli/cli" = "latest";
        "aqua:derailed/k9s" = "latest";
        "aqua:jqlang/jq" = "latest";
        "aqua:kubernetes-sigs/kustomize" = "latest";
        "aqua:kubernetes/kubernetes/kubectl" = "latest";
        "aqua:openai/codex" = "latest";
        "asdf:mise-plugins/mise-gcloud" = "latest";
        "core:java" = "latest";
        "core:node" = "latest";
      };
      settings = {
        all_compile = false;
        experimental = true;
        # disable_backends = [ "asdf" ];
      };
    };
  };
}
