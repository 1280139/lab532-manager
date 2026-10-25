# -*- coding: utf-8 -*-
"""数据库连接与迁移。

迁移机制：migrations/*.sql 按文件名排序执行，已执行的版本记在 schema_version 表。
这样上线后加字段不需要删库，也不会重复执行。
"""

from __future__ import annotations

import glob
import os
import sqlite3

from flask import current_app, g


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        db = sqlite3.connect(current_app.config["DB_PATH"], timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        db.execute("PRAGMA journal_mode = WAL")
        g.db = db
    return g.db


def close_db(exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_app(app):
    app.teardown_appcontext(close_db)


# ---------------------------------------------------------------- 迁移
SCHEMA_VERSION_DDL = """
CREATE TABLE IF NOT EXISTS schema_version (
  version    TEXT PRIMARY KEY,
  applied_at TEXT NOT NULL
)
"""


def migration_dir() -> str:
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "migrations")


def applied_versions(db: sqlite3.Connection) -> set[str]:
    db.execute(SCHEMA_VERSION_DDL)
    return {r["version"] for r in db.execute("SELECT version FROM schema_version")}


def migrate(db: sqlite3.Connection | None = None, verbose: bool = False) -> list[str]:
    """执行未应用的迁移，返回本次应用的版本列表。"""
    own = db is None
    if own:
        db = sqlite3.connect(current_app.config["DB_PATH"], timeout=10)
        db.row_factory = sqlite3.Row

    db.executescript(SCHEMA_VERSION_DDL)
    done = {r["version"] for r in db.execute("SELECT version FROM schema_version")}

    files = sorted(glob.glob(os.path.join(migration_dir(), "*.sql")))
    newly = []
    for path in files:
        version = os.path.basename(path)[:-4]
        if version in done:
            continue
        with open(path, encoding="utf-8") as f:
            db.executescript(f.read())
        db.execute(
            "INSERT INTO schema_version(version, applied_at) VALUES(?, datetime('now','localtime'))",
            (version,),
        )
        db.commit()
        newly.append(version)
        if verbose:
            print(f"  已应用迁移 {version}")

    if own:
        db.close()
    return newly


def current_version(db: sqlite3.Connection) -> str:
    db.execute(SCHEMA_VERSION_DDL)
    rows = db.execute("SELECT version FROM schema_version ORDER BY version DESC LIMIT 1").fetchall()
    return rows[0]["version"] if rows else "（未初始化）"
