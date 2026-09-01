#!/usr/bin/env python3
"""classify.py の回帰テスト。

ここが壊れると「ast-grep を使っていない」と「分類器が壊れている」が
見分けられなくなる（このリポジトリが ast-grep MCP / codegraph で 2 度踏んだ形）。
だから **当たるはずのケース** と **当たってはいけないケース** の両方を固定する。
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import classify as C

FAIL = []

def check(desc, got, want):
    if got != want:
        FAIL.append(f"{desc}\n    got : {got}\n    want: {want}")

def cats(cmd):
    return C.classify_bash(cmd)[0]

# --- 当たるべき ---
check("ast-grep 素", cats("ast-grep --lang ruby -p 'where($$$)' app/"), {"cli:ast-grep"})
check("ast-grep フルパス", cats("/opt/homebrew/bin/ast-grep scan -r r.yml"), {"cli:ast-grep"})
check("sg run", cats("sg run -p 'foo($$$)' --lang ruby"), {"cli:ast-grep"})
check("パイプで2つ", cats("git diff | grep -n foo"), {"cli:git", "cli:grep"})
check("cm add", cats('cm add "x" --category tooling'), {"cli:cm"})
check("br list", cats("br list --all"), {"cli:br"})
check("gog sheets", cats('gog sheets get ID "S!A1:B2" -p'), {"cli:gog"})
check("bin/rspec + env", cats("OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES bin/rspec spec/models"), {"cli:rspec"})
check("bundle exec rubocop", cats("bundle exec rubocop --server app/x.rb"), {"cli:rubocop"})
check("heroku run rails runner", cats("heroku run -a hrg-production -- rails runner -"), {"cli:heroku"})
check("&& 連結", cats("cd /tmp && ast-grep -p 'x' ."), {"cli:ast-grep"})
check("agent-browser", cats("agent-browser open http://localhost:3000"), {"cli:agent-browser"})
check("kt", cats("kt record get --app 45 --dry-run"), {"cli:kt"})
check("gh pr view", cats("gh pr view 2532 --json state"), {"cli:gh"})

# --- 当たってはいけない（誤検出の防止） ---
check("grep のパターンに ast-grep という文字列",
      cats("grep -rn 'ast-grep' docs/"), {"cli:grep"})
check("sg はサブコマンドが無ければ ast-grep でない",
      cats("sg foo"), {"builtin:Bash"})
check("msg は sg ではない", cats("echo msg"), {"builtin:Bash"})
check("クォート内の ; で割らない",
      cats("grep -n 'a;rm -rf /' f"), {"cli:grep"})
check("ヒアドキュメント本文は数えない",
      cats("cat > s.py <<'PY'\nimport subprocess\nsubprocess.run(['grep','x'])\nPY\npython3 s.py"),
      {"cli:python"})
check("cm はサブコマンド必須", cats("cm"), {"builtin:Bash"})
check("該当なしは Bash", cats("ls -la"), {"builtin:Bash"})

# --- MCP / ビルトイン ---
check("serena（LSP 必須の操作は lsp にも入る）",
      C.classify("mcp__serena__find_symbol", {})[0], {"mcp:serena", "lsp"})
check("serena（LSP 不要の操作は lsp に入らない）",
      C.classify("mcp__serena__activate_project", {})[0], {"mcp:serena"})
check("LSP ツール", C.classify("LSP", {"path": "app/x.rb"})[0], {"builtin:LSP", "lsp"})
check("ruby-lsp 直接起動", cats("printf '' | ruby-lsp"), {"cli:ruby-lsp"})
check("ruby-lsp は lsp にも入る",
      C.classify("Bash", {"command": "printf '' | ruby-lsp"})[0], {"cli:ruby-lsp", "lsp"})
check("serena detail", C.classify("mcp__serena__find_symbol", {})[1], "find_symbol")
check("context7", C.classify("mcp__context7__query-docs", {})[0], {"mcp:context7"})
check("未知の MCP も自動分類", C.classify("mcp__brand-new__do_it", {})[0], {"mcp:brand-new"})
check("Skill", C.classify("Skill", {"skill": "ast-grep"})[0], {"builtin:Skill", "skill:ast-grep"})
check("Grep ツール", C.classify("Grep", {"pattern": "foo"})[0], {"builtin:Grep"})
check("Agent は委譲先も独立カテゴリにする",
      C.classify("Agent", {"subagent_type": "code-investigator"})[0],
      {"builtin:Agent", "agent:code-investigator"})
check("Agent（委譲先未指定）", C.classify("Agent", {})[0], {"builtin:Agent"})

# --- シェル構文・ラッパの引数を代表コマンドにしない（実測で for/until/900 が上位に出た） ---
check("for ループ", cats('for i in 1 2 3; do echo "$i"; done'), {"builtin:Bash"})
check("until ループ", cats("until [ -f x ]; do sleep 1; done"), {"builtin:Bash"})
check("timeout の数値を拾わない", C.command_heads("timeout 900 python3 x.py"), ["python3"])
check("bq", cats('bq query --nouse_legacy_sql "select 1"'), {"cli:bq"})
check("gcloud", cats("gcloud auth list"), {"cli:gcloud"})
check("curl とパイプ", cats("curl -s https://x | jq ."), {"cli:curl", "cli:jq"})

# --- head_command ---
check("head: bin/rspec は rspec", C.command_heads("bin/rspec spec/"), ["rspec"])
check("head: パイプ2段", C.command_heads("cat f | jq .a | head -3"), ["cat", "jq", "head"])

if FAIL:
    print(f"FAIL {len(FAIL)} 件\n")
    for f in FAIL:
        print("  " + f)
    sys.exit(1)
print("classify.py: 全テスト PASS")
