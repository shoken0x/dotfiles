set nu
set nocompatible
syntax on
filetype on
"filetype indent on
filetype plugin on
set expandtab "ソフトtabを有効に
set tabstop=2 shiftwidth=2 softtabstop=2 "インデント幅を2文字に
"set autoindent "オートインデントを有効に
set nosi "smartindentを無効

"<C-Space>でomni補完
imap <Nul> <C-x><C-o>

" erbでシンタックスハイライト
autocmd BufRead,BufNewFile *.ejs set filetype=ejs.jsp

set cursorline
highlight CursorLine ctermbg=Blue
highlight CursorLine ctermfg=White

"新しいウィンドウを下へ追加
set splitbelow

"実行時間を表示
let g:quickrun_config = {'*': {'hook/time/enable': '1'},}

"for vundle
"Vim を起動して :BundleInstall
"set rtp+=~/.vim/vundle/   "vundleのディレクトリ
"call vundle#rc()
"Bundle 'thinca/vim-quickrun'

"filetype plugin indent on     " required!

