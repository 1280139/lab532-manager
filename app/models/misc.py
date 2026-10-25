# -*- coding: utf-8 -*-
"""请假与值日。"""

from __future__ import annotations

from datetime import datetime

from ..db import get_db


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ---------------------------------------------------------------- 请假
def create_leave(user_id: int, day: str, kind: str, half: str, reason: str) -> int:
    db = get_db()
    cur = db.execute(
        """INSERT INTO leaves(user_id,date,kind,half,reason,status,created_at)
           VALUES(?,?,?,?,?,'pending',?)""",
        (user_id, day, kind, half, reason, now_str()),
    )
    db.commit()
    return cur.lastrowid


def leave_by_id(lid: int):
    return get_db().execute("SELECT * FROM leaves WHERE id=?", (lid,)).fetchone()


def set_leave_status(lid: int, status: str, approver_id: int) -> None:
    db = get_db()
    db.execute(
        "UPDATE leaves SET status=?, approver_id=? WHERE id=?",
        (status, approver_id, lid),
    )
    db.commit()


def pending_leaves(teacher_id: int | None) -> list:
    db = get_db()
    sql = """SELECT l.*, s.name FROM leaves l JOIN users s ON s.id=l.user_id
             WHERE l.status='pending'"""
    params: list = []
    if teacher_id is not None:
        sql += " AND s.advisor_id=?"
        params.append(teacher_id)
    return db.execute(sql + " ORDER BY l.date", params).fetchall()


def approved_month(user_id: int, month_key: str) -> list:
    return get_db().execute(
        """SELECT * FROM leaves WHERE user_id=? AND status='approved' AND date LIKE ?""",
        (user_id, month_key + "%"),
    ).fetchall()


def recent_leaves(user_id: int, limit: int = 10) -> list:
    return get_db().execute(
        "SELECT * FROM leaves WHERE user_id=? ORDER BY date DESC LIMIT ?",
        (user_id, limit),
    ).fetchall()


# ---------------------------------------------------------------- 值日
def week_duty(start: str, end: str) -> list:
    return get_db().execute(
        """SELECT d.*, s.name FROM duty d JOIN users s ON s.id=d.user_id
           WHERE d.date>=? AND d.date<=? ORDER BY d.date, s.name""",
        (start, end),
    ).fetchall()


def assign(day: str, user_id: int) -> None:
    db = get_db()
    db.execute("INSERT OR IGNORE INTO duty(date,user_id) VALUES(?,?)", (day, user_id))
    db.commit()


def mark(duty_id: int, done: int, note: str) -> None:
    db = get_db()
    db.execute("UPDATE duty SET done=?, note=? WHERE id=?", (done, note, duty_id))
    db.commit()


def remove(duty_id: int) -> None:
    db = get_db()
    db.execute("DELETE FROM duty WHERE id=?", (duty_id,))
    db.commit()
