# -*- coding: utf-8 -*-
"""考勤核算服务：把原始打卡数据 + 请假 + 规则引擎 算成考勤明细与分数。

关键设计：
- 起算日 = 本月第一条考勤记录。制度执行前/系统上线前的日子不算缺勤，
  否则整月无数据会导致所有人考勤分清零（这是真实踩过的坑）。
- 结果可复现：同样输入永远得到同样输出，便于事后核对。
"""

from __future__ import annotations

from datetime import date

from .. import rules as R
from ..models import attendance as att_model
from ..models import misc as misc_model


def month_detail(user_id: int, month_key: str) -> dict:
    """返回 {'score', 'total_deduction', 'breakdown', 'days', 'start_date'}"""
    rows = att_model.month_rows(user_id, month_key)
    by_date = {r["date"]: r for r in rows}

    leaves = misc_model.approved_month(user_id, month_key)
    leave_map = {l["date"]: l for l in leaves}

    today = date.today()
    all_days = R.month_days(month_key)

    recorded = [date.fromisoformat(r["date"]) for r in rows]
    if not recorded:
        res = R.attendance_month([])
        res["start_date"] = None
        return res

    start = max(all_days[0], min(recorded))

    daily = []
    for day in all_days:
        if day < start or day > today:
            continue
        ds = day.isoformat()
        row = by_date.get(ds)
        lv = leave_map.get(ds)
        if lv:
            leave = {"kind": lv["kind"], "half": lv["half"]}
        elif row and row["leave_kind"]:
            leave = {"kind": row["leave_kind"], "half": row["leave_half"]}
        else:
            leave = None

        st, pts, note = R.judge_attendance(
            row["check_in"] if row else None,
            row["check_out"] if row else None,
            leave,
            day,
        )
        daily.append(
            {
                "date": day,
                "status": st,
                "deduction": pts,
                "note": note,
                "row": row,
                "makeup": bool(row and row["makeup"]),
            }
        )

    res = R.attendance_month(daily)
    res["start_date"] = start
    return res


def month_score(user_id: int, month_key: str) -> float:
    return month_detail(user_id, month_key)["score"]


def week_cells(user_id: int, monday: date) -> list:
    """本周 5 个工作日的打卡状态，供学生首页展示。"""
    from datetime import timedelta

    rows = att_model.range_rows(
        user_id, monday.isoformat(), (monday + timedelta(days=6)).isoformat()
    )
    by_date = {r["date"]: r for r in rows}
    today = date.today()

    cells = []
    for i in range(5):
        day = monday + timedelta(days=i)
        row = by_date.get(day.isoformat())
        st, pts, note = R.judge_attendance(
            row["check_in"] if row else None,
            row["check_out"] if row else None,
            {"kind": row["leave_kind"], "half": row["leave_half"]}
            if row and row["leave_kind"] else None,
            day,
        )
        cells.append(
            {
                "date": day,
                "status": st,
                "points": pts,
                "note": note,
                "row": row,
                "is_today": day == today,
                "is_future": day > today,
            }
        )
    return cells
