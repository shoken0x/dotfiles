syntax on

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

set background=dark
colorscheme solarized
let g:solarized_termcolors=256
"undoファイルを一箇所で管理
set undodir=/home/fujisaki/.vim/undo

" NeoBundle がインストールされていない時、
" もしくは、プラグインの初期化に失敗した時の処理
function! s:WithoutBundles()
  colorscheme desert
  " その他の処理
endfunction

" NeoBundle よるプラグインのロードと各プラグインの初期化
function! s:LoadBundles()
  " 読み込むプラグインの指定
  NeoBundle 'Shougo/neobundle.vim'
  NeoBundle 'tpope/vim-surround'
  NeoBundle 'tpope/vim-rails'
  NeoBundleLazy 'Shougo/unite.vim', {
  \   'autoload' : {
  \       'commands' : [ "Unite", "UniteWithBufferDir", "UniteWithCurrentDir" ]
  \   }
  \}
  NeoBundle 'Shougo/neomru.vim'
  if has('lua')
    NeoBundleLazy 'Shougo/neocomplete', {
    \   'depends' : ['Shougo/neosnippet', 'Shougo/context_filetype.vim'],
    \   'autoload' : {
    \       'insert' : 1,
    \   }
    \}
  endif
  " colorschemes
  NeoBundle 'ujihisa/unite-colorscheme'
  NeoBundle 'nanotech/jellybeans.vim'
  NeoBundle 'w0ng/vim-hybrid'
  NeoBundle 'vim-scripts/twilight'
  NeoBundle 'jonathanfilip/vim-lucius'
  NeoBundle 'jpo/vim-railscasts-theme'
  NeoBundle 'altercation/vim-colors-solarized'
  NeoBundle 'vim-scripts/Wombat'
  NeoBundle 'tomasr/molokai'
  NeoBundle 'vim-scripts/rdark'

  " ...
  " 読み込んだプラグインの設定
  " ...
  " for Unite
  let g:unite_enable_start_insert=1
  " for neomru
  let g:neomru#time_format = "(%Y/%m/%d %H:%M:%S) "
  noremap :um :Unite file_mru

endfunction

" NeoBundle がインストールされているなら LoadBundles() を呼び出す
" そうでないなら WithoutBundles() を呼び出す
function! s:InitNeoBundle()
  if isdirectory(expand("~/.vim/bundle/neobundle.vim/"))
    filetype plugin indent off
    if has('vim_starting')
      set runtimepath+=~/.vim/bundle/neobundle.vim/
    endif
    try
      call neobundle#rc(expand('~/.vim/bundle/'))
      call s:LoadBundles()
    catch
      call s:WithoutBundles()
    endtry 
  else
    call s:WithoutBundles()
  endif

  filetype indent plugin on
  syntax on
endfunction

call s:InitNeoBundle()

" neocomplete用設定
if neobundle#is_installed('neocomplete')
  let g:neocomplete#enable_at_startup = 1
  let g:neocomplete#enable_ignore_case = 1
  let g:neocomplete#enable_smart_case = 1
  let g:neocomplete#force_overwrite_completefunc = 1

  if !exists('g:neocomplete#keyword_patterns')
      let g:neocomplete#keyword_patterns = {}
  endif
  let g:neocomplete#keyword_patterns._ = '\h\w*'

  if !exists('g:neocomplete#force_omni_input_patterns')
      let g:neocomplete#force_omni_input_patterns = {}
    endif
  let g:neocomplete#force_omni_input_patterns.ruby = '[^. *\t]\.\w*\|\h\w*::'
  inoremap <expr><TAB> pumvisible() ? "\<C-n>" : "\<TAB>"
  inoremap <expr><S-TAB> pumvisible() ? "\<C-p>" : "\<S-TAB>"
endif

filetype  plugin indent on
