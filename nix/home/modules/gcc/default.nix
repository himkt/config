# Copied from https://github.com/momeemt/config.
{
  pkgs,
  ...
}:

let
  materialColors = {
    red = "38;5;203";
    amber = "38;5;214";
    blue = "38;5;33";
    green = "38;5;71";
    purple = "38;5;127";
    gray = "38;5;245";
    cyan = "38;5;81";
  };
  bold = "01";
in
{
  programs = {
    gcc = {
      enable = true;
      package = pkgs.gcc;
      colors = {
        error = "${bold};${materialColors.red}";
        warning = "${bold};${materialColors.amber}";
        note = "${bold};${materialColors.blue}";
        locus = materialColors.gray;
        quote = materialColors.gray;
        path = materialColors.cyan;
        range1 = materialColors.green;
        range2 = materialColors.blue;
        fixit-insert = materialColors.green;
        fixit-delete = materialColors.red;
        diff-filename = "${bold};${materialColors.blue}";
        diff-hunk = materialColors.purple;
        diff-delete = materialColors.red;
        diff-insert = materialColors.green;
        type-diff = "${bold};${materialColors.purple}";
        fnname = "${bold};${materialColors.green}";
        targs = materialColors.purple;
        valid = materialColors.green;
        invalid = materialColors.red;
        highlight-a = "${bold};${materialColors.blue}";
        highlight-b = "${bold};${materialColors.amber}";
      };
    };
  };
}
