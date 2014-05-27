syntax on
filetype plugin indent on 
filetype indent on

set nocompatible            " vi非互換モード
set number                  " 行番号表示
set showmode                " モード表示
set title                   " 編集中のファイル名を表示
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

" erbでシンタックスハイライト
autocmd BufRead,BufNewFile *.ejs set filetype=ejs.jsp

set cursorline " カレント行をハイライト
highlight CursorLine ctermbg=Blue
highlight CursorLine ctermfg=White

set wrapscan
set ignorecase  "検索文字列が小文字の場合は大文字小文字を区別なく検索する
set smartcase "検索文字列に大文字が含まれている場合は区別して検索する
set noincsearch "検索文字列入力時に順次対象文字列にヒットさせない
set encoding=utf8

"カーソルを表示行で移動する。物理行移動は<C-n>,<C-p>
nnoremap j gj
nnoremap k gk
nnoremap <Down> gj
nnoremap <Up>   gk

" RSense
let g:rsenseHome = "/Users/fujisaki/.vim/rsense-0.3/"
" キーバインド変更
imap <C-x> <C-x><C-o>
" 自動補完 autocomplpop.vimが必要
" let g:rsenseUseOmniFunc = 1

"新しいウィンドウを下へ追加
"set splitbelow

"実行時間を表示
"let g:quickrun_config = {'*': {'hook/time/enable': '1'},}

set background=dark
colorscheme solarized
let g:solarized_termcolors=256
