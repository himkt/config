{ ... }:

{
  services.keyd = {
    enable = true;
    keyboards.default = {
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
}
