ln -s ~/git/dotfiles/_zshrc ~/.zshrc
ln -s ~/git/dotfiles/_zprofile ~/.zprofile
ln -s ~/git/dotfiles/_gitconfig ~/.gitconfig
ln -s ~/git/dotfiles/_irbrc ~/.irbrc
ln -s ~/git/dotfiles/_gemrc ~/.gemrc
ln -s ~/git/dotfiles/_vimrc ~/.vimrc
ln -s ~/git/dotfiles/_config ~/.config
ln -s ~/git/dotfiles/_p10k.zsh ~/.p10k.zsh

# --- Claude Code ---
# ~/.claude は会話ログ・認証・DB を抱える実行時ディレクトリなので、ディレクトリごとでは
# なく「設定として手で書いたものだけ」を個別に symlink する。
mkdir -p ~/.claude/toolstats ~/.claude/skills
ln -s ~/git/dotfiles/_claude/CLAUDE.md              ~/.claude/CLAUDE.md
ln -s ~/git/dotfiles/_claude/settings.json          ~/.claude/settings.json
ln -s ~/git/dotfiles/_claude/statusline-command.sh  ~/.claude/statusline-command.sh
ln -s ~/git/dotfiles/_claude/hooks                  ~/.claude/hooks
ln -s ~/git/dotfiles/_claude/commands               ~/.claude/commands
for f in classify.py collect.py db.py hook.sh report.py selftest.sh test_classify.py README.md; do
  ln -s ~/git/dotfiles/_claude/toolstats/$f ~/.claude/toolstats/$f
done
ln -s ~/git/dotfiles/_claude/skills/diagram-craft   ~/.claude/skills/diagram-craft
ln -s ~/git/dotfiles/_claude/skills/supacode-cli    ~/.claude/skills/supacode-cli
