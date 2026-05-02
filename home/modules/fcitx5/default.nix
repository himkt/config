{
  pkgs,
  ...
}:

{
  # GTK im-module settings for fcitx5 (XWayland apps)
  gtk = {
    gtk3.extraConfig.gtk-im-module = "fcitx";
    gtk4.extraConfig.gtk-im-module = "fcitx";
  };

  i18n = {
    inputMethod = {
      enable = true;
      type = "fcitx5";
      fcitx5 = {
        addons = with pkgs; [
          fcitx5-mozc
          fcitx5-gtk
        ];
        settings = {
          inputMethod = {
            "Groups/0" = {
              Name = "Default";
              "Default Layout" = "us";
              DefaultIM = "keyboard-us";
            };
            "Groups/0/Items/0" = {
              Name = "keyboard-us";
              Layout = "";
            };
            "Groups/0/Items/1" = {
              Name = "mozc";
              Layout = "";
            };
            GroupOrder = {
              "0" = "Default";
            };
          };
          globalOptions = {
            Hotkey = {
              EnumerateWithTriggerKeys = "True";
              EnumerateSkipFirst = "False";
            };
            "Hotkey/TriggerKeys" = {
              "0" = "Control+space";
            };
            Behavior = {
              ActiveByDefault = "False";
              PreeditEnabledByDefault = "True";
              ShowInputMethodInformation = "True";
              DefaultPageSize = 5;
            };
          };
          addons = {
            classicui.globalSection = {
              PreferTextIcon = "True";
            };
          };
        };
      };
    };
  };
}
