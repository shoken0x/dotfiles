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

" tmuxのウィンドウ名をvimの編集中のファイル名に設定する
if $TMUX != ""
  augroup titlesettings
    autocmd!
    autocmd BufEnter * call system("tmux rename-window " . "'[vim] " . expand("%:t") . "'")
    autocmd VimLeave * call system("tmux rename-window bash")
    autocmd BufEnter * let &titlestring = ' ' . expand("%:t")
  augroup END
endif

" タブ
ca tn tabnew

"バックアップファイルを作成しない
set nobackup

"set guifont=Monaco:h12
set guifont=Hack:h12

" dein.vim
" プラグインがインストールされるディレクトリ
let s:dein_dir = expand('~/.cache/dein')
" dein.vim 本体
let s:dein_repo_dir = s:dein_dir . '/repos/github.com/Shougo/dein.vim'

" dein.vim がなければ github から落としてくる
if &runtimepath !~# '/dein.vim'
  if !isdirectory(s:dein_repo_dir)
    execute '!git clone https://github.com/Shougo/dein.vim' s:dein_repo_dir
  endif
  execute 'set runtimepath^=' . fnamemodify(s:dein_repo_dir, ':p')
endif

" 設定開始
if dein#load_state(s:dein_dir)
  call dein#begin(s:dein_dir)

  " プラグインリストを収めた TOML ファイル
  " 予め TOML ファイルを用意しておく
  let g:rc_dir    = expand("~/.config/nvim/")
  let s:toml      = g:rc_dir . '/dein.toml'
  " let s:lazy_toml = g:rc_dir . '/dein_lazy.toml'

  " TOML を読み込み、キャッシュしておく
  call dein#load_toml(s:toml,      {'lazy': 0})
  " call dein#load_toml(s:lazy_toml, {'lazy': 1})

  " 設定終了
  call dein#end()
  call dein#save_state()
endif

" もし、未インストールものものがあったらインストール
if dein#check_install()
  call dein#install()
endif

" syntastic + rubocop
let g:syntastic_ruby_checkers = ['rubocop']

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

" Shougo/deoplete.nvim
let g:python3_host_prog="/usr/local/bin/python3"
let g:deoplete#enable_at_startup = 1

" Yggdroot/indentLine
let g:indentLine_color_gui = '#555555'
let g:indentLine_char = '|'

" for Theme
" if (has("termguicolors"))
"   set termguicolors
" endif
" set background=dark

"" Theme seoul256
" let g:seoul256_background = 234
" syntax enable
" colorscheme seoul256

"" Theme OceanicNext
" syntax enable
" colorscheme OceanicNext

"" Theme onedark
" colorscheme onedark

"" Theme lucario
syntax enable
colorscheme lucario

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
  call denite#custom#var('file_rec', 'command',
        \ ['pt', '--follow', '--nocolor', '--nogroup', '--hidden', '-g', ''])
  call denite#custom#var('grep', 'command', ['pt'])
  call denite#custom#var('grep', 'default_opts',
        \['--nogroup', '--nocolor', '--smart-case'])
  call denite#custom#var('grep', 'recursive_opts', [])
  call denite#custom#var('grep', 'pattern_opt', [])
  call denite#custom#var('grep', 'separator', ['--'])
  call denite#custom#var('grep', 'final_opts', [])
endif

cnoremap <silent> gg :<C-u>Denite grep -auto-preview -buffer-name=search-buffer-denite -default-action=vsplit<CR>
cnoremap <silent> gr :<C-u>Denite grep -auto-preview -buffer-name=search-buffer-denite -default-action=vsplit -resume<CR>
cnoremap <silent> ff :<C-u>Denite file_rec -buffer-name=search-buffer-denite<CR>

" for incsearch.vim
map /  <Plug>(incsearch-forward)
map ?  <Plug>(incsearch-backward)
map g/ <Plug>(incsearch-stay)
