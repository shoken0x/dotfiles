"""ツール呼び出しを「どの道具を使ったか」のカテゴリに分類する。

## なぜシェルコマンドまで解析するのか

可視化したい道具（ast-grep / cm / gog / kt / agent-browser / br）は **CLI** であり、
トランスクリプト上は全部 `Bash` という 1 つのツール名に潰れる。実測（2026-08-26・全 698 セッション）:

    Bash 31,809 回 / Serena 17 回 / context7 2 回

`tool_use.name` を数えるだけでは「Bash が 78%」しか分からず、
**ast-grep を使ったかどうかは見えない**。だから Bash の `command` を分解する。

## MCP サーバーはハードコードしない

`mcp__<server>__<tool>` は機械的に `mcp:<server>` へ落とす。新しい MCP を足しても
このファイルを直さなくても集計に出る（表示ラベルだけ LABELS で上書きできる）。

## 分類は「重複を許す」

`git diff | grep foo` は git と grep の両方に数える。したがって
**カテゴリ件数の合計は総呼び出し数と一致しない**。総数は events の行数で数える。
"""

import re

# ---------------------------------------------------------------------------
# シェルコマンドの分解
# ---------------------------------------------------------------------------

# コマンド位置に来ても「実際に走る道具」ではないラッパ。読み飛ばして次のトークンを見る。
# 常に透過するラッパ。これ自体は「走らせた道具」ではない。
_ALWAYS_TRANSPARENT = {
    "sudo", "nohup", "time", "command", "env", "exec", "builtin",
    "!", "xargs", "timeout", "stdbuf", "script",
    "npx", "bunx",   # 次のトークンが道具そのもの（npx prettier / bunx tsc）
}

# `exec` / `run` が続くときだけ透過するランナー。
# ⚠️ 無条件に透過すると `bundle install` の head が `install`、
#    `rbenv versions` が `versions` になる（実測で分類外リストの上位に出た）。
_RUNNER_TRANSPARENT = {"bundle", "uv", "poetry", "pipenv", "pdm", "rye"}
_RUNNER_SUBS = {"exec", "run"}

# この語の後ろに来るのは変数名や値でコマンドではない。
# ⚠️ `for f in *.rb` の `f` を道具として数えてしまうため必要（実測 42回/20ｾｯｼｮﾝ）。
_NO_COMMAND_AFTER = {"for", "select", "case", "in"}

# 読み飛ばして次のトークンを見るシェル構文語（後ろにコマンドが来る）。
_DESCEND_KEYWORDS = {
    "do", "then", "else", "if", "elif", "while", "until", "fi", "done", "esac",
    "function", "return", "break", "continue", "{", "}", "(", ")", "[[", "]]", "[", "]",
}

_ENV_ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")

# ヒアドキュメント開始（<<EOF / <<-'EOF' / <<"EOF"）
_HEREDOC = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")


def strip_heredocs(cmd: str) -> str:
    """ヒアドキュメントの本文を落とす。

    本文を残すと `cat > x.py <<'PY'` の中の Python 行が
    「コマンド」として数えられ、grep や python が水増しされる（自分が多用する形）。
    """
    lines = cmd.split("\n")
    out = []
    i = 0
    while i < len(lines):
        line = lines[i]
        out.append(line)
        m = _HEREDOC.search(line)
        i += 1
        if not m:
            continue
        delim = m.group(2)
        # 終端デリミタ行まで捨てる
        while i < len(lines) and lines[i].strip() != delim:
            i += 1
        if i < len(lines):
            i += 1  # デリミタ行そのものも捨てる
    return "\n".join(out)


def split_segments(cmd: str):
    """クォートを尊重して ; | & && || 改行 でコマンドを分割する。

    `grep -n 'a;b' f` の `;` で割ってしまうと存在しないコマンドを数えるので、
    クォート内のセパレータは無視する。
    """
    segs = []
    buf = []
    quote = None
    i = 0
    n = len(cmd)
    while i < n:
        ch = cmd[i]
        if quote:
            buf.append(ch)
            if ch == "\\" and quote == '"' and i + 1 < n:
                buf.append(cmd[i + 1])
                i += 2
                continue
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in "'\"":
            quote = ch
            buf.append(ch)
            i += 1
            continue
        if ch == "\\" and i + 1 < n:
            buf.append(cmd[i + 1])
            i += 2
            continue
        if ch in ";\n":
            segs.append("".join(buf)); buf = []; i += 1; continue
        if ch in "|&":
            # || &&  も 1 つのセパレータとして扱う
            j = i + 1
            if j < n and cmd[j] == ch:
                j += 1
            segs.append("".join(buf)); buf = []; i = j; continue
        if ch in "()":
            segs.append("".join(buf)); buf = []; i += 1; continue
        buf.append(ch)
        i += 1
    segs.append("".join(buf))
    return [s for s in (seg.strip() for seg in segs) if s]


def head_command(segment: str):
    """セグメントの「実際に走る道具」の名前を返す（basename 化・ラッパ読み飛ばし）。

    ここの精度が全ての集計の土台になる。取りこぼしと誤検出の実例は
    _NO_COMMAND_AFTER / _RUNNER_TRANSPARENT のコメントを参照。
    """
    toks = segment.split()
    i = 0
    while i < len(toks):
        tok = toks[i].strip("\"'")
        i += 1
        if not tok:
            continue
        if _ENV_ASSIGN.match(tok):
            continue
        if tok.startswith("$") or tok.startswith("#"):
            return None            # 変数展開されたコマンドは解決できない
        if "<" in tok or ">" in tok:
            continue               # リダイレクト（2>&1 など）
        base = tok.rsplit("/", 1)[-1]
        if base in _NO_COMMAND_AFTER:
            return None
        if base in _ALWAYS_TRANSPARENT or base in _DESCEND_KEYWORDS:
            continue
        if base in _RUNNER_TRANSPARENT:
            nxt = toks[i].strip("\"'") if i < len(toks) else ""
            if nxt in _RUNNER_SUBS:
                i += 1
                continue
            return base            # `bundle install` は bundle 自身
        if base.isdigit() or re.fullmatch(r"\d+(\.\d+)?[smhd]?", base):
            continue               # `timeout 900 cmd` の 900
        if base.startswith("-"):
            return None
        return base
    return None


def command_heads(cmd: str):
    """コマンド文字列から、走る道具の名前を出現順に返す。"""
    heads = []
    for seg in split_segments(strip_heredocs(cmd)):
        h = head_command(seg)
        if h:
            heads.append(h)
    return heads


# ---------------------------------------------------------------------------
# CLI カテゴリ
#   name -> (basename の集合, サブコマンド要求の正規表現 or None)
#   サブコマンド要求は `cm` `br` `sg` のような短い名前の誤検出を防ぐため
# ---------------------------------------------------------------------------

CLI_RULES = [
    ("ast-grep",      {"ast-grep"},                          None),
    ("ast-grep",      {"sg"},        re.compile(r"^\s*(run|scan|new|test|-p\b|--pattern\b)")),
    ("rg",            {"rg"},                                None),
    ("grep",          {"grep", "egrep", "fgrep", "ugrep", "zgrep"}, None),
    ("gh",            {"gh"},                                None),
    ("kt",            {"kt"},                                None),
    ("gog",           {"gog"},                               None),
    ("cm",            {"cm"},        re.compile(r"^\s*(add|context|similar|ls|stats|doctor|playbook)\b")),
    ("br",            {"br"},        re.compile(r"^\s*(create|list|show|update|close|ready|dep|search)\b")),
    ("ntn",           {"ntn"},                               None),
    ("ee",            {"ee"},        re.compile(r"^\s*(recall|capture|search|status|doctor)\b")),
    ("agent-browser", {"agent-browser"},                     None),
    ("claude",        {"claude"},                            None),
    ("heroku",        {"heroku"},                            None),
    ("git",           {"git"},                               None),
    ("rspec",         {"rspec"},                             None),
    ("rubocop",       {"rubocop"},                           None),
    ("rails",         {"rails"},                             None),
    ("haml-lint",     {"haml-lint"},                         None),
    ("npm",           {"npm", "yarn", "pnpm"},               None),
    ("python",        {"python", "python3"},                 None),
    ("ruby",          {"ruby"},                              None),
    ("jq",            {"jq"},                                None),
    ("docker",        {"docker"},                            None),
    ("psql",          {"psql"},                              None),
    ("find",          {"find", "fd"},                        None),
    ("sed/awk",       {"sed", "awk", "perl"},                None),
    # --- 以下、標準ではなくこの環境に自分で入れた道具 ---
    ("bq",            {"bq"},                                None),
    ("gcloud",        {"gcloud", "gsutil"},                  None),
    ("cass",          {"cass"},                              None),
    ("supacode",      {"supacode"},                          None),
    ("obsidian",      {"obs", "obsidian-cli"},               None),
    ("defuddle",      {"defuddle"},                          None),
    ("skills",        {"skills"},                            None),
    ("magick",        {"magick", "convert", "ffmpeg"},       None),
    ("curl",          {"curl", "wget", "http", "httpie"},    None),
    ("bun/node",      {"bun", "node", "deno", "tsx"},        None),
    ("aws",           {"aws"},                               None),
    ("fly",           {"fly", "flyctl"},                     None),
    ("supabase",      {"supabase"},                          None),
    ("clasp",         {"clasp"},                             None),
    ("colima",        {"colima"},                            None),
    ("pdftotext",     {"pdftotext", "pdfimages", "qpdf"},    None),
    ("shellcheck",    {"shellcheck"},                        None),
    ("front-lint",    {"prettier", "eslint", "tsc", "tailwindcss", "esbuild"}, None),
    ("jest",          {"jest"},                              None),
    ("gem/rake",      {"gem", "rake", "rbenv"},              None),
    ("sqlite3",       {"sqlite3"},                           None),
    ("osv-scanner",   {"osv-scanner", "brakeman", "bundler-audit"}, None),
    ("cc-hooks",      {"claude-code-hooks", "cch-regroup-vault", "cch-save-by-repo"}, None),
    ("ruby-lsp",      {"ruby-lsp", "solargraph", "srb", "sorbet"}, None),
]


# 表示上「何をしたか」を語らない下働き。代表コマンドを選ぶときは後回しにする。
_TRIVIAL = {
    "cd", "echo", "printf", "ls", "cat", "mkdir", "pwd", "true", "false",
    "set", "export", "head", "tail", "wc", "sort", "uniq", "tr", "cut",
    "tee", "touch", "rm", "cp", "mv", "which", "type", "basename", "dirname",
    "chmod", "stat", "date", "sleep", "read", "eval", "source", ".",
}


def classify_bash(cmd: str):
    """Bash の command から (カテゴリ集合, 代表コマンド名) を返す。

    代表コマンドは **CLI ルールに当たったものを優先**する。`cd x && ast-grep -p ...` を
    `cd` と表示してしまうと、リアルタイム表示で肝心の道具が見えないため。
    """
    cmd = cmd or ""
    segs = split_segments(strip_heredocs(cmd))
    cats = set()
    first = None
    matched_head = None
    nontrivial = None
    for seg in segs:
        h = head_command(seg)
        if not h:
            continue
        if first is None:
            first = h
        if nontrivial is None and h not in _TRIVIAL:
            nontrivial = h
        rest = seg.split(h, 1)[-1] if h in seg else ""
        for name, bases, subre in CLI_RULES:
            if h in bases and (subre is None or subre.match(rest)):
                cats.add("cli:" + name)
                if matched_head is None:
                    matched_head = h
    if not cats:
        cats.add("builtin:Bash")
    return cats, matched_head or nontrivial or first


_MCP = re.compile(r"^mcp__([A-Za-z0-9_.-]+)__(.+)$")

# 言語サーバ（Ruby なら ruby-lsp）が生きていないと成立しない Serena の操作。
#
# ⚠️ `ruby-lsp` バイナリの直接起動は全期間で 1 回しかない（Serena と SessionStart hook が
# 起動するもので、こちらから叩くものではない）。したがって「ruby-lsp を使ったか」を
# コマンド名で数えると永久に 0 になり、何も分からない。
# 実際に言語サーバを動かしているのは下記の操作なので、これを合成カテゴリ `lsp` として数える。
#
# activate_project / get_current_config / *_memory / search_for_pattern / list_dir は
# LSP を必要としないので除外する（含めると「LSP が生きている」の証拠にならない）。
_LSP_BACKED_SERENA = {
    "find_symbol", "find_referencing_symbols", "find_declaration", "find_implementations",
    "get_diagnostics_for_file", "get_symbols_overview",
    "replace_symbol_body", "insert_before_symbol", "insert_after_symbol",
    "rename_symbol", "safe_delete_symbol",
}


def classify(tool_name: str, tool_input) -> tuple:
    """1 回のツール呼び出しを (カテゴリ集合, 表示用 detail) にする。"""
    tool_name = tool_name or "?"
    tool_input = tool_input if isinstance(tool_input, dict) else {}

    m = _MCP.match(tool_name)
    if m:
        server, op = m.group(1), m.group(2)
        cats = {"mcp:" + server}
        if server == "serena" and op in _LSP_BACKED_SERENA:
            cats.add("lsp")
        return cats, op

    if tool_name == "LSP":
        return {"builtin:LSP", "lsp"}, str(tool_input.get("path") or "")[:40]

    if tool_name == "Bash":
        cats, head = classify_bash(tool_input.get("command") or "")
        if "cli:ruby-lsp" in cats:
            cats.add("lsp")
        return cats, head or "bash"

    if tool_name == "Skill":
        skill = tool_input.get("skill") or ""
        return {"builtin:Skill", "skill:" + skill} if skill else {"builtin:Skill"}, skill

    if tool_name in ("Agent", "Task"):
        # 委譲先も独立カテゴリにする。プロジェクトが定義したサブエージェント
        # （code-investigator / glossary-reviewer / migration-reviewer）を
        # 実際に使ったかは、これが無いと測れない。
        sub = str(tool_input.get("subagent_type") or "").strip()
        cats = {"builtin:Agent"}
        if sub:
            cats.add("agent:" + sub)
        return cats, sub or "(指定なし)"

    detail = ""
    if tool_name in ("Read", "Edit", "Write", "NotebookEdit"):
        p = tool_input.get("file_path") or ""
        detail = p.rsplit("/", 1)[-1]
    elif tool_name == "Grep":
        detail = str(tool_input.get("pattern") or "")[:30]
    elif tool_name == "ToolSearch":
        detail = str(tool_input.get("query") or "")[:30]
    return {"builtin:" + tool_name}, detail


# ---------------------------------------------------------------------------
# 表示設定
#   focus = ステータスラインに 0 件でも常に出す道具（使ったか否かを見たいもの）
# ---------------------------------------------------------------------------

LABELS = {
    "mcp:serena":            ("srn",  "Serena MCP"),
    "mcp:context7":          ("c7",   "context7 MCP"),
    "mcp:github":            ("ghM",  "GitHub MCP"),
    "mcp:kintone":           ("ktM",  "Kintone MCP"),
    "mcp:figma":             ("fig",  "Figma MCP"),
    "mcp:claude-in-chrome":  ("chr",  "Chrome MCP"),
    "mcp:codebase-memory-mcp": ("cbm", "codebase-memory MCP"),
    "cli:ast-grep":          ("sg",   "ast-grep (CLI)"),
    "cli:grep":              ("grep", "shell grep"),
    "cli:rg":                ("rg",   "ripgrep"),
    "cli:gh":                ("gh",   "gh CLI"),
    "cli:kt":                ("kt",   "kt CLI"),
    "cli:gog":               ("gog",  "gog CLI"),
    "cli:cm":                ("cm",   "cm (cass memory)"),
    "cli:br":                ("br",   "br (beads)"),
    "cli:ntn":               ("ntn",  "ntn (Notion)"),
    "cli:ee":                ("ee",   "ee"),
    "cli:agent-browser":     ("ab",   "agent-browser"),
    "cli:heroku":            ("hrk",  "heroku CLI"),
    "cli:git":               ("git",  "git"),
    "cli:rspec":             ("spec", "rspec"),
    "cli:rubocop":           ("cop",  "rubocop"),
    "cli:rails":             ("rls",  "rails"),
    "cli:python":            ("py",   "python"),
    "cli:bq":                ("bq",   "bq (BigQuery)"),
    "cli:gcloud":            ("gcl",  "gcloud/gsutil"),
    "cli:cass":              ("cass", "cass (index)"),
    "cli:supacode":          ("spc",  "supacode CLI"),
    "cli:obsidian":          ("obs",  "obsidian-cli"),
    "cli:defuddle":          ("dfd",  "defuddle"),
    "cli:skills":            ("skls", "skills CLI"),
    "cli:magick":            ("mgk",  "ImageMagick/ffmpeg"),
    "cli:curl":              ("curl", "curl/wget"),
    "cli:bun/node":          ("node", "bun/node/deno"),
    "cli:aws":               ("aws",  "aws CLI"),
    "cli:fly":               ("fly",  "fly CLI"),
    "cli:supabase":          ("sup",  "supabase CLI"),
    "cli:clasp":             ("clsp", "clasp (GAS)"),
    "cli:colima":            ("clm",  "colima"),
    "cli:pdftotext":         ("pdf",  "pdftotext/poppler"),
    "cli:shellcheck":        ("shck", "shellcheck"),
    "cli:front-lint":        ("fe",   "prettier/eslint/tsc"),
    "cli:jest":              ("jest", "jest"),
    "cli:gem/rake":          ("gem",  "gem/rake/rbenv"),
    "cli:sqlite3":           ("sql",  "sqlite3"),
    "cli:osv-scanner":       ("osv",  "osv-scanner/brakeman"),
    "cli:cc-hooks":          ("cch",  "claude-code-hooks"),
    "lsp":                   ("lsp",  "LSP 経由の解決"),
    "cli:ruby-lsp":          ("rlsp", "ruby-lsp / solargraph（直接起動）"),
    "builtin:LSP":           ("LSP",  "LSP ツール"),
    # cinv = code-investigator。短縮の由来を聞かれたので出典を残す:
    # sg は ast-grep 公式の2つ目のバイナリ名（brew の同一 formula が両方入れる）だが、
    # cinv はこちらで付けた略。
    "agent:code-investigator":  ("cinv", "agent: code-investigator"),
    "agent:general-purpose":    ("gp",   "agent: general-purpose"),
    "agent:Explore":            ("expl", "agent: Explore"),
    "agent:glossary-reviewer":  ("glos", "agent: glossary-reviewer"),
    "agent:migration-reviewer": ("migr", "agent: migration-reviewer"),
    "cli:ruby":              ("rb",   "ruby"),
    "cli:jq":                ("jq",   "jq"),
    "cli:find":              ("find", "find/fd"),
    "cli:sed/awk":           ("sed",  "sed/awk/perl"),
    "cli:docker":            ("dkr",  "docker"),
    "cli:psql":              ("psql", "psql"),
    "cli:npm":               ("npm",  "npm/yarn"),
    "cli:claude":            ("cc",   "claude CLI"),
    "cli:haml-lint":         ("haml", "haml-lint"),
    "builtin:Bash":          ("sh",   "Bash (その他)"),
    "builtin:Grep":          ("Grep", "Grep ツール"),
    "builtin:Read":          ("Read", "Read ツール"),
    "builtin:Edit":          ("Edit", "Edit ツール"),
    "builtin:Write":         ("Writ", "Write ツール"),
    "builtin:Agent":         ("agt",  "サブエージェント"),
    "builtin:Skill":         ("skl",  "Skill 呼び出し"),
    "builtin:WebFetch":      ("web",  "WebFetch"),
    "builtin:WebSearch":     ("wsr",  "WebSearch"),
    "builtin:ToolSearch":    ("tsr",  "ToolSearch"),
}

# --- ステータスラインの2段構え -------------------------------------------------
#
# FOCUS = **0 でも常に表示する**。「代替手段があるのに選ばなかった」が読み取れる道具だけを置く。
#   ast-grep ⇄ grep / Serena ⇄ Edit / context7 ⇄ Web / cm ⇄ 記録しない /
#   agent-browser ⇄ Chrome MCP / code-investigator ⇄ general-purpose /
#   lsp ⇄ grep+Read（合成カテゴリ。_LSP_BACKED_SERENA のコメントを参照）
#   → ここが 0 なら「別の道を選んだ」という意味になる。
#
# WATCH = **使ったときだけ表示する**。作業領域で決まる道具（その作業が無ければ 0 が当然）。
#   gog は Sheets 作業、kt は Kintone 作業、ntn は Notion 作業が無ければ 0 になる。
#   常時 `gog·0` を出しても情報が無いので、非 0 のときだけ出す。
#
# 上書き: CLAUDE_TOOLSTATS_FOCUS / CLAUDE_TOOLSTATS_WATCH（カンマ区切り）
DEFAULT_FOCUS = [
    "cli:ast-grep",
    "mcp:serena",
    "mcp:context7",
    "cli:cm",
    "cli:agent-browser",
    "agent:code-investigator",
    "lsp",
]

DEFAULT_WATCH = [
    "cli:gog", "cli:kt", "cli:ntn", "cli:br", "cli:ee", "cli:cass",
    "cli:bq", "cli:gcloud", "cli:heroku", "cli:supacode", "cli:obsidian",
    "cli:ruby-lsp",
    "mcp:figma", "mcp:claude-in-chrome", "mcp:supabase", "mcp:github", "mcp:kintone",
    "agent:glossary-reviewer", "agent:migration-reviewer", "agent:Explore",
    "agent:general-purpose",
]

# 「どちらを選んだか」の対比。優劣の採点ではなく選択比の可視化。
RIVALS = [
    ("cli:ast-grep", ["cli:grep", "cli:rg", "builtin:Grep"], "構造検索: ast-grep vs grep 系"),
    ("lsp",          ["cli:grep", "builtin:Grep", "builtin:Read"], "シンボル解決: LSP 経由 vs grep/Read"),
    ("mcp:serena",   ["builtin:Edit", "builtin:Write"],       "シンボル編集: Serena vs Edit/Write"),
    ("mcp:context7", ["builtin:WebFetch", "builtin:WebSearch"], "ライブラリ調査: context7 vs Web"),
    ("mcp:github",   ["cli:gh"],                              "GitHub: MCP vs gh CLI"),
    ("mcp:kintone",  ["cli:kt"],                              "Kintone: MCP vs kt CLI"),
]


def label(key: str) -> str:
    if key in LABELS:
        return LABELS[key][0]
    if key.startswith("mcp:"):
        return key[4:][:4]
    if key.startswith("cli:"):
        return key[4:][:5]
    if key.startswith("skill:"):
        return key[6:][:6]
    if key.startswith("agent:"):
        return key[6:][:6]
    return key.split(":", 1)[-1][:5]


def display_name(key: str) -> str:
    if key in LABELS:
        return LABELS[key][1]
    if key.startswith("mcp:"):
        return key[4:] + " MCP"
    if key.startswith("cli:"):
        return key[4:] + " (CLI)"
    if key.startswith("skill:"):
        return "skill: " + key[6:]
    if key.startswith("agent:"):
        return "agent: " + key[6:]
    return key.split(":", 1)[-1]
