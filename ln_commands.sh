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

# --- git identity ---
# 氏名・メールは PUBLIC のこのリポジトリに置かず、追跡しない ~/.gitconfig.local に置く
# （_gitconfig が [include] で読み込む）。作らないと author 未設定でコミットできない。
cat > ~/.gitconfig.local <<'GITID'
[user]
	name = shoken
	email = <自分のメールアドレス>
GITID
chmod 600 ~/.gitconfig.local

# --- git-secrets ---
# _gitconfig の [init] templateDir が指すテンプレートを実際に作る。
# 🔴 symlink では足りない。テンプレートは git-secrets 本体が生成するものなので、
#    このリポジトリには入っておらず、新しいマシンでは必ずここを踏む。
# 作られていないと 2つ壊れる:
#   1. git clone / git init のたびに
#      "warning: templates not found in ~/.git-templates/git-secrets" が出る
#   2. git 既定のテンプレートが使われなくなり、**.git/hooks が作られない**
#      （= git-secrets の pre-commit も入らず、秘密情報の検査が一切効かない）
brew install git-secrets
git secrets --install ~/.git-templates/git-secrets

# ⚠️ templateDir が効くのは `git init` / `git clone` のときだけ。
#    既にクローン済みのリポジトリには各々で入れる:  cd <repo> && git secrets --install
