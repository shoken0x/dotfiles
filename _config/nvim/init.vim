set nu
syntax on
inoremap <silent> jj <ESC>
cnoremap nh nohlsearch
set autoread                " 他でファイルが編集された時に自動で読み込む

autocmd BufWritePre * :%s/\s\+$//ge " 行末の空白を削除
set expandtab "タブの代わりに空白文字挿入
set tabstop=2 shiftwidth=2 softtabstop=2 "インデント幅を2文字に
set autoindent "オートインデントを有効に

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

colorscheme desert
