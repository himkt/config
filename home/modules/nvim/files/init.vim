" vim: ft=vim
"
" ---------------------
"
" NeoVim configuration
"
" @author = 'himkt'
"
" ---------------------
"

"" disable mouse
set mouse=

"" use python3 installed globally
let g:python3_host_prog=$PYTHONSYSTEMPATH

"" load basic vim configuration
source $XDG_CONFIG_HOME/nvim/vimrc

" material.vim
if (has('nvim'))
  let $NVIM_TUI_ENABLE_TRUE_COLOR = 1
endif

if (has('termguicolors'))
  set termguicolors
endif

hi Normal guibg=NONE ctermbg=NONE
hi Visual guibg=gray

" tabular
vnoremap tr :<C-u> Tabularize /

" vim-indent-guide
let g:indent_guides_enable_on_vim_startup = 1
