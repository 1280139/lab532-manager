# -*- coding: utf-8 -*-
"""月度考评服务 —— 系统的核心，也是"真用"与"练习项目"的分界线。

三件事必须做对：

1. **规则版本化**：每条考评记录写明按哪版手册算的（rule_version）。
   手册每年更新，历史记录不能因为改了常量就变。

2. **计算留痕（快照）**：把当时的考勤分、周报字数、排名、档位
   全部存成 JSON。事后有人质疑"为什么王五只有 350 元"，
   能拿出当时的原始依据，而不是重新算一遍（数据可能已变）。

3. **强制分布不挤占**：本月一次周报都没交的人，任务分记 0，
   且**不参与排名**，否则会挤掉别人的档位。
"""

from __future__ import annotations

import json
from datetime import datetime

from .. import rules as R
from ..db import get_db
from ..models import reports as rep_model
from ..models import users as user_model
from . import attendance_service


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def get_eval(user_id: int, month_key: str):
    return get_db().execute(
        "SELECT * FROM evaluations WHERE user_id=? AND month_key=?", (user_id, month_key)
    ).fetchone()


def list_evals(month_key: str) -> dict[int, object]:
    rows = get_db().execute(
        "SELECT * FROM evaluations WHERE month_key=?", (month_key,)
    ).fetchall()
    return {r["user_id"]: r for r in rows}


def set_enable_score(user_id: int, month_key: str, score: float) -> None:
    db = get_db()
    db.execute(
        """INSERT INTO evaluations(user_id,month_key,rule_version,enable_score,updated_at)
           VALUES(?,?,?,?,?)
           ON CONFLICT(user_id,month_key) DO UPDATE SET
             enable_score=excluded.enable_score, updated_at=excluded.updated_at""",
        (user_id, month_key, R.RULE_VERSION, score, now_str()),
    )
    db.commit()


def compute_month(month_key: str, teacher_id: int | None) -> list[dict]:
    """生成某月考评。返回本次的计算结果列表（含快照）。"""
    students = user_model.all_students(teacher_id)
    if not students:
        return []

    db = get_db()

    # ---------- 1. 收集每个学生的原始依据 ----------
    raws = []
    for s in students:
        reports = rep_model.month_reports(s["id"], month_key[:4])
        # 只看该月的周报（week_key 形如 2026-W43，需按年月过滤）
        month_reports = [r for r in reports if _week_in_month(r["week_key"], month_key)]

        att = attendance_service.month_detail(s["id"], month_key)

        if month_reports:
            avg_wc = sum(r["word_count"] for r in month_reports) / len(month_reports)
            raw_score = avg_wc + len(month_reports) * 30
        else:
            avg_wc = 0.0
            raw_score = 0.0

        raws.append(
            {
                "student": s,
                "att": att,
                "n_reports": len(month_reports),
                "avg_wc": round(avg_wc, 1),
                "raw_score": round(raw_score, 1),
                "report_weeks": [r["week_key"] for r in month_reports],
            }
        )

    # ---------- 2. 强制分布（排除本月零周报者） ----------
    eligible = [i for i, r in enumerate(raws) if r["n_reports"] > 0]
    sub_scores = [raws[i]["raw_score"] for i in eligible]
    sub_alloc = R.forced_distribution(sub_scores)

    alloc = [None] * len(raws)
    for pos, i in enumerate(eligible):
        alloc[i] = sub_alloc[pos]

    # ---------- 3. 合成 S 值、等级、金额，并落库 ----------
    results = []
    for i, r in enumerate(raws):
        s = r["student"]
        att_score = r["att"]["score"]

        if r["n_reports"] == 0:
            task_score = 0.0
            bucket = "—"
            rank = 0
            extra_note = "本月未提交周报，任务分按 0 计"
        else:
            task_score = alloc[i]["score"]
            bucket = alloc[i]["bucket"]
            rank = alloc[i]["rank"]
            extra_note = ""

        prev = get_eval(s["id"], month_key)
        enable_score = prev["enable_score"] if prev else 0.0

        S = R.compute_s(att_score, task_score, enable_score)
        grade, ratio, note = R.grade_and_payout(S, att_score)
        if extra_note:
            note = f"{extra_note}；{note}" if note else extra_note

        base = R.base_allowance(s["degree"] or "master", s["assist_type"])
        amount = R.final_amount(base, ratio)

        snapshot = {
            "rule_version": R.RULE_VERSION,
            "month": month_key,
            "generated_at": now_str(),
            "attendance": {
                "score": att_score,
                "total_deduction": r["att"]["total_deduction"],
                "start_date": r["att"].get("start_date").isoformat()
                if r["att"].get("start_date") else None,
                "breakdown": r["att"]["breakdown"],
                "days": [
                    {
                        "date": d["date"].isoformat(),
                        "status": d["status"],
                        "deduction": d["deduction"],
                        "note": d["note"],
                    }
                    for d in r["att"]["days"]
                ],
            },
            "reports": {
                "count": r["n_reports"],
                "weeks": r["report_weeks"],
                "avg_word_count": r["avg_wc"],
                "raw_rank_score": r["raw_score"],
                "rank": rank,
                "bucket": bucket,
                "task_score": task_score,
            },
            "enable_score": enable_score,
            "formula": "S = 考勤*0.4 + 任务*0.6 + 赋能*0.3",
            "s_value": S,
            "grade": grade,
            "ratio": ratio,
            "base_amount": base,
            "final_amount": amount,
        }

        db.execute(
            """INSERT INTO evaluations(user_id,month_key,rule_version,attendance_score,
                 task_score,enable_score,s_value,grade,ratio,base_amount,final_amount,
                 snapshot,note,finalized,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,1,?)
               ON CONFLICT(user_id,month_key) DO UPDATE SET
                 rule_version=excluded.rule_version,
                 attendance_score=excluded.attendance_score,
                 task_score=excluded.task_score,
                 enable_score=excluded.enable_score,
                 s_value=excluded.s_value, grade=excluded.grade,
                 ratio=excluded.ratio, base_amount=excluded.base_amount,
                 final_amount=excluded.final_amount, snapshot=excluded.snapshot,
                 note=excluded.note, finalized=1, updated_at=excluded.updated_at""",
            (
                s["id"], month_key, R.RULE_VERSION, att_score, task_score,
                enable_score, S, grade, ratio, base, amount,
                json.dumps(snapshot, ensure_ascii=False), note, now_str(),
            ),
        )

        results.append(
            {
                "student": s,
                "attendance_score": att_score,
                "task_score": task_score,
                "enable_score": enable_score,
                "s_value": S,
                "grade": grade,
                "ratio": ratio,
                "base_amount": base,
                "final_amount": amount,
                "bucket": bucket,
                "rank": rank,
                "n_reports": r["n_reports"],
                "note": note,
            }
        )

    db.commit()
    return results


def _week_in_month(week_key: str, month_key: str) -> bool:
    """判断 ISO 周是否属于某月：取该周的周一，看它落在哪个月。"""
    from datetime import date

    try:
        y, w = week_key.split("-W")
        monday = date.fromisocalendar(int(y), int(w), 1)
    except (ValueError, AttributeError):
        return False
    return monday.strftime("%Y-%m") == month_key
