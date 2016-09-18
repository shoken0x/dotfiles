set number
set noswapfile
set cursorline
set clipboard+=unnamedplus
inoremap <silent> jj <ESC>
cnoremap nh nohlsearch
set autoread                " 他でファイルが編集された時に自動で読み込む

autocmd BufWritePre * :%s/\s\+$//ge " 行末の空白を削除
set expandtab "タブの代わりに空白文字挿入
set tabstop=2 shiftwidth=2 softtabstop=2 "インデント幅を2文字に
set autoindent "オートインデントを有効に
filetype plugin indent on

" tmuxのウィンドウ名をvimの編集中のファイル名に設定する
if $TMUX != ""
  augroup titlesettings
    autocmd!
    autocmd BufEnter * call system("tmux rename-window " . "'[vim] " . expand("%:t") . "'")
    autocmd VimLeave * call system("tmux rename-window zsh")
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
let g:deoplete#enable_at_startup = 1

" for Theme
if (has("termguicolors"))
  set termguicolors
endif

"" Theme seoul256
" let g:seoul256_background = 234
" syntax enable
" colorscheme seoul256

"" Theme OceanicNext
" syntax enable
" colorscheme OceanicNext
" set background=dark

syntax enable
colorscheme onedark
highlight CursorLine cterm=NONE guibg=#444444
