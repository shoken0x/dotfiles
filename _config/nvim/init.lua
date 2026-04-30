vim.g.loaded_ruby_provider = 0
vim.g.loaded_perl_provider = 0
vim.g.loaded_node_provider = 0
vim.g.loaded_python3_provider = 0

vim.g.mapleader = " "

local opt = vim.opt
opt.number = true
opt.swapfile = false
opt.backup = false
opt.cursorline = true
opt.autoread = true
opt.clipboard:append("unnamedplus")
opt.expandtab = true
opt.tabstop = 2
opt.shiftwidth = 2
opt.softtabstop = 2
opt.autoindent = true

local map = vim.keymap.set
map("i", "jj", "<ESC>", { silent = true })
map("c", "nh", "nohlsearch")
map("n", "<ESC><ESC>", ":nohlsearch<CR>", { silent = true })
map("t", "<ESC>", [[<C-\><C-n>]], { silent = true })
map("n", "<Leader>w", ":w<CR>")
map("n", "<Leader><Leader>", "<C-v>")

vim.cmd([[cnoreabbrev tn tabnew]])

local au = vim.api.nvim_create_autocmd

au("BufWritePre", {
  desc = "行末の空白を削除",
  pattern = "*",
  command = [[silent! %s/\s\+$//e]],
})

au("BufReadPost", {
  desc = "最後にカーソルがあった場所に移動",
  pattern = "*",
  callback = function()
    local last_line = vim.fn.line([['"]])
    if last_line > 0 and last_line <= vim.fn.line("$") then
      vim.cmd([[normal! g`"]])
    end
  end,
})

au("TermOpen", {
  desc = "ターミナルを開いたら Insert モードで開始",
  pattern = "*",
  command = "startinsert",
})

vim.pack.add({
  { src = "https://github.com/catppuccin/nvim", name = "catppuccin" },
  { src = "https://github.com/stevearc/conform.nvim" },
})

require("catppuccin").setup({
  flavour = "macchiato",
  transparent_background = true,
})
vim.cmd.colorscheme("catppuccin")

require("conform").setup({
  formatters_by_ft = {
    javascript = { "prettier" },
    javascriptreact = { "prettier" },
    typescript = { "prettier" },
    typescriptreact = { "prettier" },
    json = { "prettier" },
    jsonc = { "prettier" },
    css = { "prettier" },
    html = { "prettier" },
    markdown = { "prettier" },
    yaml = { "prettier" },
  },
  format_on_save = {
    timeout_ms = 1000,
    lsp_format = "fallback",
  },
})
