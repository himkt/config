{
  config,
  pkgs,
  lib,
  ...
}:

let
  src = ./files;
in

{
  home.file = {
    ".claude/CLAUDE.md".source = src + "/CLAUDE.md";
    ".claude/README.md".source = src + "/README.md";
    ".claude/settings.json".source = src + "/settings.json";
    ".claude/.mcp.json".source = src + "/.mcp.json";
    ".claude/agents".source = src + "/agents";
    ".claude/bin".source = src + "/bin";
    ".claude/rules".source = src + "/rules";
    ".claude/skills" = { source = src + "/skills"; recursive = true; };
  };
}
