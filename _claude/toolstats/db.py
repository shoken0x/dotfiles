"""toolstats の SQLite ストア。

## なぜ SQLite か

- **並列セッションが常態**（worktree を複数開く運用）。TSV への追記だと
  ロックとオフセット管理を自作することになる。SQLite は WAL + busy_timeout で済む
- `tid`（tool_use の id）を主キーにするので、**オフセットがずれても二重計上しない**（冪等）
- ダッシュボードの集計が SQL の GROUP BY で終わる

## テーブル

- `files`     … 走査済みバイトオフセット（増分読み込み用）
- `events`    … ツール呼び出し 1 回 = 1 行
- `event_cats`… 1 呼び出しが複数カテゴリに当たる（`git diff | grep` 等）ので別テーブル
- `hook_fires`… hook の発火（`attachment.type == "hook_success"` 由来）
- `exposure`  … その MCP が「載っていた」セッション（採用率の母数）
"""

import os
import sqlite3

ROOT = os.path.expanduser(os.environ.get("CLAUDE_TOOLSTATS_DIR", "~/.claude/toolstats"))
DB_PATH = os.path.join(ROOT, "toolstats.db")
STATE_DIR = os.path.join(ROOT, "state")

SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS files (
  path       TEXT PRIMARY KEY,
  size       INTEGER NOT NULL DEFAULT 0,
  offset     INTEGER NOT NULL DEFAULT 0,
  mtime      REAL    NOT NULL DEFAULT 0,
  scanned_at INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS events (
  tid     TEXT PRIMARY KEY,
  ts      INTEGER NOT NULL,
  day     TEXT    NOT NULL,
  session TEXT    NOT NULL,
  origin  TEXT    NOT NULL,
  repo    TEXT,
  branch  TEXT,
  tool    TEXT    NOT NULL,
  detail  TEXT,
  head    TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_day     ON events(day);
CREATE INDEX IF NOT EXISTS idx_events_session ON events(session);
CREATE INDEX IF NOT EXISTS idx_events_ts      ON events(ts);

CREATE TABLE IF NOT EXISTS event_cats (
  tid TEXT NOT NULL,
  cat TEXT NOT NULL,
  PRIMARY KEY (tid, cat)
);
CREATE INDEX IF NOT EXISTS idx_event_cats_cat ON event_cats(cat);

CREATE TABLE IF NOT EXISTS hook_fires (
  uid         TEXT PRIMARY KEY,
  ts          INTEGER NOT NULL,
  day         TEXT    NOT NULL,
  session     TEXT    NOT NULL,
  origin      TEXT    NOT NULL,
  atype       TEXT,
  event       TEXT,
  hook_name   TEXT,
  command     TEXT,
  tool_use_id TEXT,
  label       TEXT
);
CREATE INDEX IF NOT EXISTS idx_hook_day ON hook_fires(day);

CREATE TABLE IF NOT EXISTS exposure (
  session TEXT NOT NULL,
  cat     TEXT NOT NULL,
  day     TEXT,
  PRIMARY KEY (session, cat)
);

CREATE TABLE IF NOT EXISTS sessions (
  session  TEXT PRIMARY KEY,
  first_ts INTEGER,
  last_ts  INTEGER,
  repo     TEXT,
  branch   TEXT
);
"""


def connect():
    os.makedirs(ROOT, exist_ok=True)
    os.makedirs(STATE_DIR, exist_ok=True)
    con = sqlite3.connect(DB_PATH, timeout=30.0)
    con.execute("PRAGMA busy_timeout=30000")
    con.executescript(SCHEMA)
    return con
