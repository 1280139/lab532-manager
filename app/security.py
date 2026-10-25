# -*- coding: utf-8 -*-
"""安全相关：密码哈希、CSRF、登录态、审计日志。

密码用 werkzeug 的 scrypt 哈希（Flask 自带依赖，无需额外安装）。
兼容旧库的明文密码：首次登录成功时自动升级为哈希。
"""

from __future__ import annotations

import functools
import hmac
import os
import secrets

from flask import (abort, current_app, g, redirect, request, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

from .db import get_db

# ---------------------------------------------------------------- 密码
HASH_PREFIXES = ("scrypt:", "pbkdf2:", "argon2")


def hash_password(raw: str) -> str:
    return generate_password_hash(raw, method="scrypt")


def is_hashed(stored: str) -> bool:
    return stored is not None and stored.startswith(HASH_PREFIXES)


def verify_password(stored: str, raw: str) -> tuple[bool, bool]:
    """返回 (是否通过, 是否需要升级为哈希)。"""
    if is_hashed(stored):
        return check_password_hash(stored, raw), False
    # 旧库明文密码：仅在允许回退时接受，登录后立刻升级
    if not current_app.config.get("ALLOW_PLAIN_PASSWORD_FALLBACK"):
        return False, False
    ok = hmac.compare_digest(stored or "", raw)
    return ok, ok


# ---------------------------------------------------------------- CSRF
CSRF_SESSION_KEY = "_csrf_token"


def csrf_token() -> str:
    tok = session.get(CSRF_SESSION_KEY)
    if not tok:
        tok = secrets.token_urlsafe(32)
        session[CSRF_SESSION_KEY] = tok
    return tok


def check_csrf() -> None:
    """所有非 GET 请求统一校验。失败直接 400。"""
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return
    expect = session.get(CSRF_SESSION_KEY)
    got = request.form.get("_csrf") or request.headers.get("X-CSRF-Token")
    if not expect or not got or not hmac.compare_digest(expect, got):
        abort(400, description="CSRF 校验失败，请刷新页面重试")


# ---------------------------------------------------------------- 登录态
def current_user():
    if "user" in g:
        return g.user
    uid = session.get("uid")
    if not uid:
        g.user = None
        return None
    row = get_db().execute(
        "SELECT * FROM users WHERE id=? AND active=1", (uid,)
    ).fetchone()
    g.user = row
    return row


def login_user(user_row) -> None:
    session.clear()
    session["uid"] = user_row["id"]
    session.permanent = True   # 启用 PERMANENT_SESSION_LIFETIME 超时


def logout_user() -> None:
    session.clear()


def login_required(f):
    @functools.wraps(f)
    def wrapper(*a, **kw):
        if not current_user():
            return redirect(url_for("auth.login", next=request.path))
        return f(*a, **kw)

    return wrapper


def role_required(*roles):
    def deco(f):
        @functools.wraps(f)
        def wrapper(*a, **kw):
            u = current_user()
            if not u:
                return redirect(url_for("auth.login"))
            if u["role"] not in roles:
                abort(403)
            return f(*a, **kw)

        return wrapper

    return deco


# ---------------------------------------------------------------- 审计
def audit(action: str, target: str = "", detail: str = "") -> None:
    """写审计日志。注意：调用方需自行 commit，避免和业务事务分裂。"""
    u = current_user()
    db = get_db()
    db.execute(
        """INSERT INTO audit_log(user_id,action,target,detail,ip,created_at)
           VALUES(?,?,?,?,?,datetime('now','localtime'))""",
        (
            u["id"] if u else None,
            action,
            target,
            detail,
            request.remote_addr or "",
        ),
    )


def get_db_commit() -> None:
    """提交当前连接的挂起写入（供 audit 之后调用）。"""
    get_db().commit()


def init_app(app):
    """注册 CSRF 全局钩子与模板变量。"""

    @app.before_request
    def _csrf_guard():
        check_csrf()

    @app.context_processor
    def _inject():
        return {"csrf_token": csrf_token, "current_user": current_user}
