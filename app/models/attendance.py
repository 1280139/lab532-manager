# -*- coding: utf-8 -*-
"""考勤读写。"""

from __future__ import annotations

from datetime import datetime

from ..db import get_db


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def get(user_id: int, day: str):
    return get_db().execute(
        "SELECT * FROM attendance WHERE user_id=? AND date=?", (user_id, day)
    ).fetchone()


def month_rows(user_id: int, month_key: str) -> list:
    return get_db().execute(
        "SELECT * FROM attendance WHERE user_id=? AND date LIKE ?",
        (user_id, month_key + "%"),
    ).fetchall()


def range_rows(user_id: int, start: str, end: str) -> list:
    return get_db().execute(
        "SELECT * FROM attendance WHERE user_id=? AND date>=? AND date<=? ORDER BY date",
        (user_id, start, end),
    ).fetchall()


def ensure_row(user_id: int, day: str) -> None:
    db = get_db()
    db.execute(
        "INSERT OR IGNORE INTO attendance(user_id,date,created_at) VALUES(?,?,?)",
        (user_id, day, now_str()),
    )
    db.commit()


def set_time(user_id: int, day: str, field: str, hhmm: str) -> None:
    assert field in ("check_in", "check_out")
    db = get_db()
    db.execute(
        f"UPDATE attendance SET {field}=? WHERE user_id=? AND date=?",
        (hhmm, user_id, day),
    )
    db.commit()


def makeup_count(user_id: int, month_key: str) -> int:
    return get_db().execute(
        "SELECT COUNT(*) c FROM attendance WHERE user_id=? AND makeup=1 AND date LIKE ?",
        (user_id, month_key + "%"),
    ).fetchone()["c"]


def set_makeup(user_id: int, day: str, check_in: str, check_out: str) -> None:
    db = get_db()
    db.execute(
        """UPDATE attendance SET
             check_in=COALESCE(NULLIF(?,''), check_in),
             check_out=COALESCE(NULLIF(?,''), check_out),
             makeup=1
           WHERE user_id=? AND date=?""",
        (check_in, check_out, user_id, day),
    )
    db.commit()


def today_missing(teacher_id: int | None, today: str) -> list:
    """今日未打卡的学生。"""
    db = get_db()
    sql = """SELECT u.* FROM users u
             WHERE u.role='student' AND u.active=1
               AND NOT EXISTS (SELECT 1 FROM attendance a
                               WHERE a.user_id=u.id AND a.date=? AND a.check_in IS NOT NULL)"""
    params: list = [today]
    if teacher_id is not None:
        sql += " AND u.advisor_id=?"
        params.append(teacher_id)
    return db.execute(sql + " ORDER BY u.id", params).fetchall()
