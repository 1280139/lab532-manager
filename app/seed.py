# -*- coding: utf-8 -*-
"""种子数据：仅开发/演示环境使用。

密码全部经过哈希，种子数据里不出现任何明文密码。
"""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta

from . import rules as R
from .security import hash_password

DEFAULT_PASSWORD = "lab532demo"   # 仅演示用，首次登录后应提示修改


def seed(db: sqlite3.Connection) -> None:
    if db.execute("SELECT COUNT(*) c FROM users").fetchone()["c"] > 0:
        return

    now = date.today()
    cur = db.cursor()
    pwd = hash_password(DEFAULT_PASSWORD)

    cur.execute(
        "INSERT INTO users(name,account,password,role) VALUES(?,?,?,?)",
        ("实验室管理员", "admin", pwd, "admin"),
    )
    cur.execute(
        "INSERT INTO users(name,account,password,role) VALUES(?,?,?,?)",
        ("张老师", "t001", pwd, "teacher"),
    )
    tid = cur.lastrowid

    students = [
        ("张三", "s001", "master", "II", "2025"),
        ("李四", "s002", "master", "I", "2025"),
        ("王五", "s003", "master", "II", "2024"),
        ("赵六", "s004", "phd", None, "2023"),
        ("孙七", "s005", "master", "I", "2025"),
    ]
    sids = []
    for name, acc, deg, at, grade in students:
        cur.execute(
            """INSERT INTO users(name,account,password,role,degree,assist_type,grade,advisor_id)
               VALUES(?,?,?,?,?,?,?,?)""",
            (name, acc, pwd, "student", deg, at, grade, tid),
        )
        sids.append(cur.lastrowid)

    def workdays(n: int) -> list[date]:
        out, d0 = [], now - timedelta(days=1)
        while len(out) < n:
            if not R.is_weekend(d0):
                out.append(d0)
            d0 -= timedelta(days=1)
        return list(reversed(out))

    days = workdays(10)

    # 张三：良好，偶有迟到
    for i, day in enumerate(days):
        ci, co = ("08:25", "21:05") if i % 4 else ("08:47", "21:10")
        cur.execute(
            "INSERT OR IGNORE INTO attendance(user_id,date,check_in,check_out,created_at) VALUES(?,?,?,?,?)",
            (sids[0], day.isoformat(), ci, co, day.isoformat() + " 21:05:00"),
        )

    # 李四：正常，一天事假
    for i, day in enumerate(days):
        if i == 3:
            cur.execute(
                "INSERT OR IGNORE INTO attendance(user_id,date,leave_kind,leave_half,created_at) VALUES(?,?,?,?,?)",
                (sids[1], day.isoformat(), "personal", "full", day.isoformat() + " 08:00:00"),
            )
        else:
            cur.execute(
                "INSERT OR IGNORE INTO attendance(user_id,date,check_in,check_out,created_at) VALUES(?,?,?,?,?)",
                (sids[1], day.isoformat(), "08:20", "21:00", day.isoformat() + " 21:00:00"),
            )

    # 王五：问题学生，缺勤 2 天、严重迟到、早退
    for i, day in enumerate(days):
        if i in (2, 6):
            continue
        if i == 4:
            cur.execute(
                "INSERT OR IGNORE INTO attendance(user_id,date,check_in,created_at) VALUES(?,?,?,?)",
                (sids[2], day.isoformat(), "09:40", day.isoformat() + " 09:40:00"),
            )
        elif i == 7:
            cur.execute(
                "INSERT OR IGNORE INTO attendance(user_id,date,check_in,check_out,created_at) VALUES(?,?,?,?,?)",
                (sids[2], day.isoformat(), "08:35", "19:30", day.isoformat() + " 19:30:00"),
            )
        else:
            cur.execute(
                "INSERT OR IGNORE INTO attendance(user_id,date,check_in,check_out,created_at) VALUES(?,?,?,?,?)",
                (sids[2], day.isoformat(), "08:40", "21:00", day.isoformat() + " 21:00:00"),
            )

    # 赵六（博士）：全勤
    for day in days:
        cur.execute(
            "INSERT OR IGNORE INTO attendance(user_id,date,check_in,check_out,created_at) VALUES(?,?,?,?,?)",
            (sids[3], day.isoformat(), "08:15", "21:30", day.isoformat() + " 21:30:00"),
        )

    # 孙七：正常
    for day in days:
        cur.execute(
            "INSERT OR IGNORE INTO attendance(user_id,date,check_in,check_out,created_at) VALUES(?,?,?,?,?)",
            (sids[4], day.isoformat(), "08:28", "21:00", day.isoformat() + " 21:00:00"),
        )

    # 请假：王五下周一病假待审批
    next_mon = R.week_monday(now) + timedelta(days=7)
    cur.execute(
        """INSERT INTO leaves(user_id,date,kind,half,reason,status,created_at)
           VALUES(?,?,?,?,?,'pending',?)""",
        (sids[2], next_mon.isoformat(), "sick", "full", "感冒发烧，需就医",
         next_mon.isoformat() + " 10:00:00"),
    )

    # 值日：本周
    monday = R.week_monday(now)
    for i in range(5):
        day = monday + timedelta(days=i)
        for sid in (sids[i % len(sids)], sids[(i + 1) % len(sids)]):
            cur.execute("INSERT OR IGNORE INTO duty(date,user_id) VALUES(?,?)",
                        (day.isoformat(), sid))

    # 上周周报
    last_week = R.week_key(now - timedelta(days=7))
    daily_text = "上午精读论文并整理公式推导，下午跑对比实验记录显存占用，晚上复盘数据。"
    seeds = [
        (sids[0], 320, "本周完成 baseline 复现第一阶段，跑通两组对比实验，整理出初步结果表。",
         "进度正常，显存问题可以试梯度累积，下周组会讲一下。"),
        (sids[1], 280, "完成数据预处理脚本，处理 5000 条样本，缺失值比例 3.2%。",
         "预处理流程没问题，注意确认数据字典。"),
        (sids[3], 420, "精读 3 篇 SCI 一区文献，完成综述框架，跑通对比方法代码。",
         "综述框架可以，下周把对比实验补齐。"),
        (sids[4], 260, "整理了实验记录，复现了 baseline 的两个模块。", ""),
    ]
    for sid, wc, summary, comment in seeds:
        cur.execute(
            """INSERT OR IGNORE INTO reports(user_id,week_key,mon,tue,wed,thu,fri,
                 summary,next_plan,word_count,submitted_at,comment)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (sid, last_week, daily_text, daily_text, daily_text, daily_text, daily_text,
             summary, "下周继续推进当前任务，完成剩余实验。", wc,
             now.isoformat() + " 20:00:00", comment or None),
        )

    db.commit()
