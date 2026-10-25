# -*- coding: utf-8 -*-
"""学生端：打卡、请假、补卡、周报。"""

from __future__ import annotations

from datetime import date, timedelta

from flask import (Blueprint, flash, redirect, render_template, request, url_for)

from .. import rules as R
from .. import security
from ..models import attendance as att_model
from ..models import misc as misc_model
from ..models import reports as rep_model
from ..services import attendance_service

bp = Blueprint("student", __name__)


@bp.before_request
@security.login_required
@security.role_required("student")
def _guard():
    return None


@bp.route("/my")
def home():
    u = security.current_user()
    today = date.today()
    monday = R.week_monday()

    att = attendance_service.month_detail(u["id"], R.month_key())
    mk = R.month_key()

    return render_template(
        "student/home.html",
        today_att=att_model.get(u["id"], today.isoformat()),
        week_cells=attendance_service.week_cells(u["id"], monday),
        report=rep_model.get(u["id"], R.week_key()),
        att_score=att["score"],
        att_breakdown=att["breakdown"],
        att_start=att.get("start_date"),
        makeup_used=att_model.makeup_count(u["id"], mk),
        makeup_limit=R.MAKEUP_LIMIT,
        active="home",
    )


@bp.route("/my/checkin", methods=["POST"])
def checkin():
    u = security.current_user()
    today = date.today()

    if R.is_weekend(today):
        flash("周末不考勤", "error")
        return redirect(url_for("student.home"))

    action = request.form.get("action", "in")
    if action not in ("in", "out"):
        flash("无效操作", "error")
        return redirect(url_for("student.home"))

    hhmm = request.form.get("time", "").strip() or date.today().strftime("%H:%M")
    if not R.hhmm_to_time(hhmm):
        flash("时间格式不对，应为 HH:MM", "error")
        return redirect(url_for("student.home"))

    day = today.isoformat()
    att_model.ensure_row(u["id"], day)
    att_model.set_time(u["id"], day, "check_in" if action == "in" else "check_out", hhmm)

    row = att_model.get(u["id"], day)
    st, pts, note = R.judge_attendance(row["check_in"], row["check_out"], None, today)
    label = "上班" if action == "in" else "下班"
    if pts:
        flash(f"{label}打卡已记录（{hhmm}），判定：{R.STATUS_CN[st]}，扣 {pts} 分", "error")
    else:
        flash(f"{label}打卡已记录（{hhmm}）", "success")

    security.audit("checkin", target=f"attendance:{day}", detail=f"{action}={hhmm}")
    security.get_db_commit()
    return redirect(url_for("student.home"))


@bp.route("/my/leave", methods=["POST"])
def leave():
    u = security.current_user()
    day = request.form.get("date", "").strip()
    kind = request.form.get("kind", "personal")
    half = request.form.get("half", "full")
    reason = request.form.get("reason", "").strip()

    d = _parse_date(day)
    if not d:
        flash("请选择请假日期", "error")
        return redirect(url_for("student.home"))
    if d <= date.today():
        flash("请假需提前 1 天提交", "error")
        return redirect(url_for("student.home"))
    if kind not in ("personal", "sick") or half not in ("full", "am", "pm"):
        flash("请假类型无效", "error")
        return redirect(url_for("student.home"))

    lid = misc_model.create_leave(u["id"], d.isoformat(), kind, half, reason)
    security.audit("leave_apply", target=f"leave:{lid}", detail=f"{d} {kind} {half}")
    security.get_db_commit()
    flash("请假申请已提交，等待导师审批", "success")
    return redirect(url_for("student.home"))


@bp.route("/my/makeup", methods=["POST"])
def makeup():
    u = security.current_user()
    d = _parse_date(request.form.get("date", "").strip())
    if not d:
        flash("请选择补卡日期", "error")
        return redirect(url_for("student.home"))

    used = att_model.makeup_count(u["id"], R.month_key(d))
    okc, msg = R.check_makeup(used, d)
    if not okc:
        flash(msg, "error")
        return redirect(url_for("student.home"))

    day = d.isoformat()
    att_model.ensure_row(u["id"], day)
    att_model.set_makeup(
        u["id"], day,
        request.form.get("check_in", "").strip(),
        request.form.get("check_out", "").strip(),
    )
    security.audit("makeup", target=f"attendance:{day}", detail=f"used={used + 1}")
    security.get_db_commit()
    flash(f"补卡成功（{day}），本月已用 {used + 1}/{R.MAKEUP_LIMIT} 次", "success")
    return redirect(url_for("student.home"))


@bp.route("/my/report", methods=["GET", "POST"])
def report():
    u = security.current_user()
    wk = request.args.get("week") or R.week_key()

    if request.method == "POST":
        wk = request.form.get("week") or R.week_key()
        daily = {d: request.form.get(d, "").strip() for d in R.REPORT_DAYS}
        summary = request.form.get("summary", "").strip()
        next_plan = request.form.get("next_plan", "").strip()
        monthly = request.form.get("monthly", "").strip()

        okc, problems = R.check_report(daily, summary, next_plan)
        if not okc:
            for p in problems:
                flash(p, "error")
            return redirect(url_for("student.report", week=wk))

        wc = R.report_word_count(daily, summary, next_plan)
        rep_model.upsert(
            u["id"], wk,
            {
                "mon": daily["周一"], "tue": daily["周二"], "wed": daily["周三"],
                "thu": daily["周四"], "fri": daily["周五"],
                "summary": summary, "next_plan": next_plan,
                "monthly": monthly, "word_count": wc,
            },
        )
        security.audit("report_submit", target=f"report:{wk}", detail=f"words={wc}")
        security.get_db_commit()
        flash(f"{wk} 工作记录已提交（{wc} 字）", "success")
        return redirect(url_for("student.home"))

    d = date.today()
    is_month_end = (d + timedelta(days=7)).month != d.month

    return render_template(
        "student/report.html",
        report=rep_model.get(u["id"], wk),
        wk=wk,
        is_current=wk == R.week_key(),
        history=rep_model.recent(u["id"]),
        is_month_end=is_month_end,
        min_chars=R.MIN_REPORT_CHARS,
        active="report",
    )


def _parse_date(s: str):
    try:
        return date.fromisoformat(s)
    except (ValueError, TypeError):
        return None
