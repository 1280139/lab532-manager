# -*- coding: utf-8 -*-
"""管理命令：初始化、迁移、建管理员、备份。

用法：
  python manage.py init          # 建库 + 迁移 + 种子数据（仅开发）
  python manage.py migrate       # 只跑迁移
  python manage.py create-admin  # 交互式创建管理员
  python manage.py backup        # 备份数据库
  python manage.py status        # 查看状态
"""

from __future__ import annotations

import getpass
import os
import shutil
import sqlite3
import sys
from datetime import datetime

from app import create_app, db
from app.config import get_config


def cmd_init(seed: bool = True):
    app = create_app()
    with app.app_context():
        path = app.config["DB_PATH"]
        print(f"数据库: {path}")
        applied = db.migrate(verbose=True)
        if applied:
            print(f"已应用 {len(applied)} 个迁移")
        else:
            print("迁移已是最新")

        if seed and app.config.get("ALLOW_PLAIN_PASSWORD_FALLBACK", True):
            from app.seed import seed as do_seed

            conn = db.get_db()
            do_seed(conn)
            n = conn.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]
            print(f"种子数据就绪，共 {n} 个用户")
        elif seed:
            print("生产模式跳过种子数据，请用 create-admin 创建管理员")


def cmd_migrate():
    app = create_app()
    with app.app_context():
        applied = db.migrate(verbose=True)
        print(f"本次应用 {len(applied)} 个迁移" if applied else "迁移已是最新")


def cmd_create_admin():
    app = create_app()
    with app.app_context():
        conn = db.get_db()
        name = input("姓名: ").strip()
        account = input("账号: ").strip()
        if not name or not account:
            print("姓名和账号不能为空")
            return
        if conn.execute("SELECT 1 FROM users WHERE account=?", (account,)).fetchone():
            print("账号已存在")
            return
        pwd = getpass.getpass("密码（至少 8 位）: ")
        if len(pwd) < 8:
            print("密码太短")
            return
        if pwd != getpass.getpass("再输一次: "):
            print("两次不一致")
            return

        from app.security import hash_password

        conn.execute(
            "INSERT INTO users(name,account,password,role) VALUES(?,?,?,'admin')",
            (name, account, hash_password(pwd)),
        )
        conn.commit()
        print(f"管理员 {name}（{account}）已创建")


def cmd_backup():
    app = create_app()
    path = app.config["DB_PATH"]
    if not os.path.exists(path):
        print("数据库不存在")
        return
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = f"{path}.backup-{stamp}"
    # 用 SQLite 的在线备份 API，保证一致性（不是简单复制文件）
    src = sqlite3.connect(path)
    dst = sqlite3.connect(dest)
    with dst:
        src.backup(dst)
    dst.close()
    src.close()
    size = os.path.getsize(dest) / 1024
    print(f"已备份到 {dest}（{size:.1f} KB）")


def cmd_status():
    app = create_app()
    with app.app_context():
        conn = db.get_db()
        print(f"环境: {os.environ.get('FLASK_ENV', 'dev')}")
        print(f"数据库: {app.config['DB_PATH']}")
        print(f"Schema 版本: {db.current_version(conn)}")
        from app import rules as R

        print(f"规则版本: {R.RULE_VERSION}（{R.RULE_SOURCE}）")
        print("\n数据量:")
        for t in ("users", "attendance", "reports", "duty", "leaves", "evaluations", "audit_log"):
            try:
                n = conn.execute(f"SELECT COUNT(*) c FROM {t}").fetchone()["c"]
                print(f"  {t:<14} {n:>5}")
            except sqlite3.OperationalError:
                print(f"  {t:<14} （表不存在）")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "init"
    {
        "init": cmd_init,
        "migrate": cmd_migrate,
        "create-admin": cmd_create_admin,
        "backup": cmd_backup,
        "status": cmd_status,
    }.get(cmd, cmd_init)()
