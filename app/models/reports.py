# -*- coding: utf-8 -*-
"""周工作记录读写。"""

from __future__ import annotations

from datetime import datetime

from ..db import get_db


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def get(user_id: int, week_key: str):
    return get_db().execute(
        "SELECT * FROM reports WHERE user_id=? AND week_key=?", (user_id, week_key)
    ).fetchone()


def recent(user_id: int, limit: int = 6) -> list:
    return get_db().execute(
        "SELECT * FROM reports WHERE user_id=? ORDER BY week_key DESC LIMIT ?",
        (user_id, limit),
    ).fetchall()


def upsert(user_id: int, week_key: str, fields: dict) -> None:
    db = get_db()
    db.execute(
        """INSERT INTO reports(user_id,week_key,mon,tue,wed,thu,fri,
             summary,next_plan,monthly,word_count,submitted_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(user_id,week_key) DO UPDATE SET
             mon=excluded.mon, tue=excluded.tue, wed=excluded.wed,
             thu=excluded.thu, fri=excluded.fri,
             summary=excluded.summary, next_plan=excluded.next_plan,
             monthly=excluded.monthly, word_count=excluded.word_count,
             submitted_at=excluded.submitted_at""",
        (
            user_id, week_key,
            fields.get("mon", ""), fields.get("tue", ""), fields.get("wed", ""),
            fields.get("thu", ""), fields.get("fri", ""),
            fields.get("summary", ""), fields.get("next_plan", ""),
            fields.get("monthly", ""), fields.get("word_count", 0), now_str(),
        ),
    )
    db.commit()


def set_comment(report_id: int, user_id: int, comment: str) -> None:
    db = get_db()
    db.execute(
        "UPDATE reports SET comment=? WHERE id=? AND user_id=?",
        (comment, report_id, user_id),
    )
    db.commit()


def month_reports(user_id: int, year: str) -> list:
    return get_db().execute(
        "SELECT * FROM reports WHERE user_id=? AND week_key LIKE ?",
        (user_id, year + "%"),
    ).fetchall()


def missing_this_week(teacher_id: int | None, week_key: str) -> list:
    db = get_db()
    sql = """SELECT u.* FROM users u
             WHERE u.role='student' AND u.active=1
               AND NOT EXISTS (SELECT 1 FROM reports r
                               WHERE r.user_id=u.id AND r.week_key=?)"""
    params: list = [week_key]
    if teacher_id is not None:
        sql += " AND u.advisor_id=?"
        params.append(teacher_id)
    return db.execute(sql + " ORDER BY u.id", params).fetchall()
