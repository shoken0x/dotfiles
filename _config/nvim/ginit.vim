GuiFont Monaco:h16
GuiLinespace 8

if exists('g:GuiLoaded')
  set hidden
  nnoremap <Leader>zo :GonvimFuzzyBLines<CR>
  nnoremap <Leader>zb :GonvimFuzzyBuffers<CR>
  nnoremap <Leader>zs :GonvimFuzzyAg<CR>
  nnoremap <Leader>zf :GonvimFuzzyFiles<CR>
endif
