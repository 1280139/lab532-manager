# -*- coding: utf-8 -*-
"""登录 / 登出 / 改密码。"""

from __future__ import annotations

from flask import (Blueprint, flash, redirect, render_template, request,
                   session, url_for)

from .. import security
from ..models import users as user_model

bp = Blueprint("auth", __name__)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        acc = request.form.get("account", "").strip()
        pwd = request.form.get("password", "").strip()

        user = user_model.by_account(acc)
        if user:
            ok, need_upgrade = security.verify_password(user["password"], pwd)
            if ok:
                # 明文密码首次登录成功后立即升级为哈希
                if need_upgrade:
                    user_model.update_password(user["id"], security.hash_password(pwd))
                security.login_user(user)
                security.audit("login", target=f"user:{user['id']}")
                security.get_db_commit()
                nxt = request.args.get("next")
                if nxt and nxt.startswith("/") and not nxt.startswith("//"):
                    return redirect(nxt)
                return redirect(url_for("index"))
        flash("账号或密码错误", "error")

    from flask import current_app

    return render_template(
        "login.html",
        show_demo=current_app.config.get("SHOW_DEMO_ACCOUNTS", False),
    )


@bp.route("/logout")
def logout():
    security.audit("logout")
    security.get_db_commit()
    security.logout_user()
    return redirect(url_for("auth.login"))


@bp.route("/password", methods=["GET", "POST"])
@security.login_required
def change_password():
    if request.method == "POST":
        old = request.form.get("old", "")
        new = request.form.get("new", "")
        confirm = request.form.get("confirm", "")

        u = security.current_user()
        ok, _ = security.verify_password(u["password"], old)
        if not ok:
            flash("原密码不正确", "error")
        elif len(new) < 8:
            flash("新密码至少 8 位", "error")
        elif new != confirm:
            flash("两次输入不一致", "error")
        elif new == old:
            flash("新密码不能与原密码相同", "error")
        else:
            user_model.update_password(u["id"], security.hash_password(new))
            security.audit("change_password", target=f"user:{u['id']}")
            security.get_db_commit()
            flash("密码已修改，请重新登录", "success")
            security.logout_user()
            return redirect(url_for("auth.login"))

    return render_template("password.html")
