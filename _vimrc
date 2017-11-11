set encoding=utf8
scriptencoding utf-8

inoremap <silent> jj <ESC>
cnoremap nh nohlsearch
" Escの2回押しでハイライト消去
nmap <ESC><ESC> :nohlsearch<CR><ESC>

set number                  " 行番号表示
set showmode                " モード表示
set title                   " 編集中のファイル名を表示
set cursorline              " カーソルラインハイライト
set ruler                   " ルーラーの表示
set showcmd                 " 入力中のコマンドをステータスに表示する
set showmatch               " 括弧入力時の対応する括弧を表示
set laststatus=2            " ステータスラインを常に表示
set display=uhex            " 表示できない文字を16進数で表示
set scrolloff=5             " 常にカーソル位置から5行余裕を取る
set virtualedit=block       " 矩形選択でカーソル位置の制限を解除
set autoread                " 他でファイルが編集された時に自動で読み込む

set list
set listchars=tab:»-,trail:▸" 不可視文字を可視化

set expandtab "タブの代わりに空白文字挿入
set tabstop=2 shiftwidth=2 softtabstop=2 "インデント幅を2文字に
"set autoindent "オートインデントを有効に
set nosi "smartindentを無効

"<C-Space>でomni補完
imap <Nul> <C-x><C-o>

" ejsでシンタックスハイライト
augroup vimrc
  autocmd!
  autocmd BufRead,BufNewFile *.ejs set filetype=ejs.jsp
augroup END

set wrapscan
set ignorecase   "検索文字列が小文字の場合は大文字小文字を区別なく検索する
set smartcase    "検索文字列に大文字が含まれている場合は区別して検索する
set noincsearch  "検索文字列入力時に順次対象文字列にヒットさせない

"カーソルを表示行で移動する。物理行移動は<C-n>,<C-p>
nnoremap j gj
nnoremap k gk
nnoremap <Down> gj
nnoremap <Up>   gk

"undoファイルを一箇所で管理
set undodir=/home/fujisaki/.vim/undo

filetype  plugin indent on
syntax on
set background=dark
colorscheme lucario
" colorscheme solarized
" let g:solarized_termcolors=256
