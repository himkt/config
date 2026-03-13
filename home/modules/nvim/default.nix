{ ... }:
{
  xdg.configFile."nvim/init.vim" = {
    source = ./files/init.vim;
  };

  xdg.configFile."nvim/vimrc" = {
    source = ./files/vimrc;
  };
}
