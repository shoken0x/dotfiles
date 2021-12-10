set number
set noswapfile
set cursorline
set clipboard+=unnamedplus
inoremap <silent> jj <ESC>
cnoremap nh nohlsearch
nmap <ESC><ESC> :nohlsearch<CR><ESC> " Escの2回押しでハイライト消去
tnoremap <silent> <ESC> <C-\><C-n> " terminalモード用
set autoread                " 他でファイルが編集された時に自動で読み込む

autocmd BufWritePre * :%s/\s\+$//ge " 行末の空白を削除
set expandtab "タブの代わりに空白文字挿入
set tabstop=2 shiftwidth=2 softtabstop=2 "インデント幅を2文字に
set autoindent "オートインデントを有効に
filetype plugin indent on

let mapleader = "\<Space>"
nnoremap <Leader>w :w<CR>
nmap <Leader><Leader> <C-v>

" 最後にカーソルがあった場所に移動
augroup vimrcEx
  au BufRead * if line("'\"") > 0 && line("'\"") <= line("$") |
  \ exe "normal g`\"" | endif
augroup END<Paste>

" tmuxのウィンドウ名をvimの編集中のファイル名に設定する
"if $TMUX != ""
"  augroup titlesettings
"    autocmd!
"    autocmd BufEnter * call system("tmux rename-window " . "'[vim] " . expand("%:t") . "'")
"    autocmd VimLeave * call system("tmux rename-window bash")
"    autocmd BufEnter * let &titlestring = ' ' . expand("%:t")
"  augroup END
"endif

" タブ
ca tn tabnew

"バックアップファイルを作成しない
set nobackup

"set guifont=Monaco:h12
set guifont=Hack:h12

" init dein
" % curl https://raw.githubusercontent.com/Shougo/dein.vim/master/bin/installer.sh > installer.sh
" % sh ./installer.sh ~/.cache/dein
if &compatible
  set nocompatible
endif
set runtimepath+=~/.cache/dein/repos/github.com/Shougo/dein.vim
if dein#load_state('~/.cache/dein')
  call dein#begin('~/.cache/dein')
  call dein#load_toml('~/.config/nvim/dein.toml', {'lazy': 0})
  call dein#end()
  call dein#save_state()
endif

" もし、未インストールものものがあったらインストール
if dein#check_install()
  call dein#install()
endif

" syntastic + rubocop
" let g:syntastic_ruby_checkers = ['rubocop']
" ale + rubocop
let g:ale_fixers = {'ruby': ['rubocop'],}
let g:ale_fix_on_save = 1

if !exists("*GitGrep")
  func GitGrep(...)
    let save = &grepprg
    set grepprg=git\ grep\ -niI\ $*
    let s = 'grep'
    for i in a:000
      let s = s . ' ' . i
    endfor
    exe s
    let &grepprg = save
  endfun
command -nargs=? G call GitGrep(<f-args>)
endif
autocmd QuickFixCmdPost *grep* cwindow

let g:python_host_prog="/usr/bin/python"
" Shougo/deoplete.nvim
let g:python3_host_prog="/usr/bin/python3"
let g:deoplete#enable_at_startup = 1

" Yggdroot/indentLine
let g:indentLine_color_gui = '#555555'
let g:indentLine_char = '|'

" for Theme
" if (has("termguicolors"))
"   set termguicolors
" endif
" set background=dark
" syntax off
syntax enable

"" Theme seoul256
" let g:seoul256_background = 234
" colorscheme seoul256

"" Theme OceanicNext
colorscheme OceanicNext

"" Theme onedark
" colorscheme onedark

"" Theme lucario
" colorscheme lucario

highlight CursorLine cterm=NONE guibg=#444444
highlight Search ctermfg=15 ctermbg=68 guifg=#ffffff guibg=#6699cc

if isdirectory(".git")
  call denite#custom#var('file_rec', 'command', ['git', 'ls-files', '-co', '--exclude-standard'])
  call denite#custom#var('grep', 'command', ['git', '--no-pager', 'grep'])
  call denite#custom#var('grep', 'recursive_opts', [])
  call denite#custom#var('grep', 'final_opts', [])
  call denite#custom#var('grep', 'separator', [])
  call denite#custom#var('grep', 'default_opts', ['-nH'])
else
  call denite#custom#var('file_rec', 'command', ['pt', '--follow', '--nocolor', '--nogroup', '--hidden', '-g', ''])
  call denite#custom#var('grep', 'command',     ['pt', '--follow', '--nocolor', '--nogroup', '--hidden', '--smart-case'])
  call denite#custom#var('grep', 'default_opts', [])
  call denite#custom#var('grep', 'recursive_opts', [])
  call denite#custom#var('grep', 'pattern_opt', [])
  call denite#custom#var('grep', 'separator', ['--'])
  call denite#custom#var('grep', 'final_opts', [])
endif

"nnoremap [denite] <Nop>
"nmap <C-d> [denite]
"nnoremap <silent> [denite]g :<C-u>Denite grep -auto-preview -buffer-name=search-buffer-denite -default-action=vsplit<CR>
"nnoremap <silent> [denite]r :<C-u>Denite grep -auto-preview -buffer-name=search-buffer-denite -default-action=vsplit -resume<CR>
"cnoremap <silent> gg :<C-u>Denite grep -auto-preview -buffer-name=search-buffer-denite -default-action=vsplit<CR>
"cnoremap <silent> gr :<C-u>Denite grep -auto-preview -buffer-name=search-buffer-denite -default-action=vsplit -resume<CR>
cnoremap <silent> gg :<C-u>Denite grep -buffer-name=search-buffer-denite -default-action=vsplit<CR>
cnoremap <silent> gr :<C-u>Denite grep -buffer-name=search-buffer-denite -default-action=vsplit -resume<CR>
cnoremap <silent> ff :<C-u>Denite file_rec -buffer-name=search-buffer-denite<CR>

" Define mappings
autocmd FileType denite call s:denite_my_settings()
function! s:denite_my_settings() abort
  nnoremap <silent><buffer><expr> <CR> denite#do_map('do_action')
  nnoremap <silent><buffer><expr> p denite#do_map('do_action', 'preview')
  nnoremap <silent><buffer><expr> q denite#do_map('quit')
  nnoremap <silent><buffer><expr> i denite#do_map('open_filter_buffer')
  nnoremap <silent><buffer><expr> <Space> denite#do_map('toggle_select').'j'
endfunction

let g:ruby_path = ""
let g:ruby_host_prog="/Users/shoken/.rbenv/shims/neovim-ruby-host"
let g:loaded_perl_provider = 0

if has('nvim')
  autocmd TermOpen term://* startinsert
endif
