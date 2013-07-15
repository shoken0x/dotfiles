syntax on
filetype on
"filetype indent on
filetype plugin on

set nocompatible "vi非互換モード
set number "行番号表示
set showmode "モード表示
set title "編集中のファイル名を表示
set ruler "ルーラーの表示
set showcmd "入力中のコマンドをステータスに表示する
set showmatch "括弧入力時の対応する括弧を表示
set laststatus=2 "ステータスラインを常に表示

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

"新しいウィンドウを下へ追加
"set splitbelow

"実行時間を表示
"let g:quickrun_config = {'*': {'hook/time/enable': '1'},}

set wrapscan
set ignorecase  "検索文字列が小文字の場合は大文字小文字を区別なく検索する
set smartcase "検索文字列に大文字が含まれている場合は区別して検索する
set noincsearch "検索文字列入力時に順次対象文字列にヒットさせない
set encoding=utf8

"for vundle
"Vim を起動して :BundleInstall
"set rtp+=~/.vim/vundle/   "vundleのディレクトリ
"call vundle#rc()
"Bundle 'thinca/vim-quickrun'
"filetype plugin indent on     " required!

