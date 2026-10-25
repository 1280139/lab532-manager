# -*- coding: utf-8 -*-
"""管理员端：用户管理、审计日志、数据备份。"""

from __future__ import annotations

from flask import (Blueprint, abort, flash, redirect, render_template, request,
                   send_file, url_for)
from io import BytesIO

from .. import rules as R
from .. import security
from ..db import get_db
from ..models import users as user_model

bp = Blueprint("admin", __name__)


@bp.before_request
@security.login_required
@security.role_required("admin")
def _guard():
    return None


@bp.route("/admin/users")
def users():
    db = get_db()
    rows = db.execute(
        "SELECT * FROM users ORDER BY role, grade DESC, id"
    ).fetchall()
    teachers = db.execute(
        "SELECT * FROM users WHERE role IN ('teacher','admin') AND active=1"
    ).fetchall()
    return render_template(
        "admin/users.html", rows=rows, teachers=teachers, active="admin"
    )


@bp.route("/admin/users/create", methods=["POST"])
def user_create():
    name = request.form.get("name", "").strip()
    account = request.form.get("account", "").strip()
    role = request.form.get("role", "student")
    password = request.form.get("password", "").strip()

    if not name or not account:
        flash("姓名和账号不能为空", "error")
        return redirect(url_for("admin.users"))
    if role not in ("admin", "teacher", "student"):
        flash("角色无效", "error")
        return redirect(url_for("admin.users"))
    if len(password) < 8:
        flash("初始密码至少 8 位", "error")
        return redirect(url_for("admin.users"))
    if user_model.by_account(account):
        flash(f"账号 {account} 已存在", "error")
        return redirect(url_for("admin.users"))

    db = get_db()
    try:
        db.execute(
            """INSERT INTO users(name,account,password,role,degree,assist_type,grade,advisor_id)
               VALUES(?,?,?,?,?,?,?,?)""",
            (
                name, account, security.hash_password(password), role,
                request.form.get("degree") or None,
                request.form.get("assist_type") or None,
                request.form.get("grade") or None,
                request.form.get("advisor_id", type=int),
            ),
        )
        db.commit()
    except Exception as e:  # noqa: BLE001
        flash(f"创建失败：{e}", "error")
        return redirect(url_for("admin.users"))

    security.audit("user_create", target=f"user:{account}", detail=f"role={role}")
    security.get_db_commit()
    flash(f"已创建 {name}（{account}）", "success")
    return redirect(url_for("admin.users"))


@bp.route("/admin/users/<int:uid>/reset", methods=["POST"])
def user_reset(uid):
    new_pwd = request.form.get("password", "").strip()
    if len(new_pwd) < 8:
        flash("新密码至少 8 位", "error")
        return redirect(url_for("admin.users"))
    user_model.update_password(uid, security.hash_password(new_pwd))
    security.audit("user_reset_password", target=f"user:{uid}")
    security.get_db_commit()
    flash("密码已重置", "success")
    return redirect(url_for("admin.users"))


@bp.route("/admin/users/<int:uid>/toggle", methods=["POST"])
def user_toggle(uid):
    db = get_db()
    row = db.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    if not row:
        abort(404)
    me = security.current_user()
    if row["id"] == me["id"]:
        flash("不能停用自己", "error")
        return redirect(url_for("admin.users"))
    db.execute("UPDATE users SET active=? WHERE id=?", (0 if row["active"] else 1, uid))
    db.commit()
    security.audit("user_toggle", target=f"user:{uid}",
                   detail=f"active={0 if row['active'] else 1}")
    security.get_db_commit()
    flash("已" + ("停用" if row["active"] else "启用"), "success")
    return redirect(url_for("admin.users"))


@bp.route("/admin/audit")
def audit_log():
    db = get_db()
    page = max(1, request.args.get("page", 1, type=int))
    size = 50
    total = db.execute("SELECT COUNT(*) c FROM audit_log").fetchone()["c"]
    rows = db.execute(
        """SELECT a.*, u.name FROM audit_log a
           LEFT JOIN users u ON u.id=a.user_id
           ORDER BY a.id DESC LIMIT ? OFFSET ?""",
        (size, (page - 1) * size),
    ).fetchall()
    return render_template(
        "admin/audit.html", rows=rows, page=page,
        pages=max(1, (total + size - 1) // size), total=total, active="admin"
    )


@bp.route("/admin/export")
def export():
    """导出全库为 SQLite 文件，用于备份。"""
    path = get_db_path()
    with open(path, "rb") as f:
        data = f.read()
    security.audit("export_db")
    security.get_db_commit()
    return send_file(
        BytesIO(data),
        mimetype="application/octet-stream",
        as_attachment=True,
        download_name=f"lab-backup-{R.month_key()}.db",
    )


@bp.route("/admin/system")
def system():
    from ..db import current_version

    db = get_db()
    stats = {}
    for t in ("users", "attendance", "reports", "duty", "leaves", "evaluations", "audit_log"):
        stats[t] = db.execute(f"SELECT COUNT(*) c FROM {t}").fetchone()["c"]
    return render_template(
        "admin/system.html", stats=stats,
        schema_version=current_version(db),
        rule_version=R.RULE_VERSION, rule_source=R.RULE_SOURCE,
        active="admin",
    )


def get_db_path() -> str:
    from flask import current_app

    return current_app.config["DB_PATH"]
