# -*- coding: utf-8 -*-
"""用户与权限相关查询。"""

from __future__ import annotations

from ..db import get_db


def by_account(account: str):
    return get_db().execute(
        "SELECT * FROM users WHERE account=? AND active=1", (account,)
    ).fetchone()


def by_id(uid: int):
    return get_db().execute(
        "SELECT * FROM users WHERE id=? AND active=1", (uid,)
    ).fetchone()


def all_students(teacher_id: int | None = None) -> list:
    """管理员传 None 看全部；导师传自己 id 看名下。"""
    db = get_db()
    if teacher_id is None:
        return db.execute(
            "SELECT * FROM users WHERE role='student' AND active=1 ORDER BY grade DESC, id"
        ).fetchall()
    return db.execute(
        """SELECT * FROM users WHERE role='student' AND active=1 AND advisor_id=?
           ORDER BY grade DESC, id""",
        (teacher_id,),
    ).fetchall()


def update_password(uid: int, hashed: str) -> None:
    db = get_db()
    db.execute("UPDATE users SET password=? WHERE id=?", (hashed, uid))
    db.commit()
