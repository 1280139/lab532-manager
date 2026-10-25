# -*- coding: utf-8 -*-
"""导师 / 管理员端：工作台、学生详情、考评、值日、审批。"""

from __future__ import annotations

from datetime import date, timedelta

from flask import (Blueprint, abort, flash, redirect, render_template, request,
                   url_for)

from .. import rules as R
from .. import security
from ..models import attendance as att_model
from ..models import misc as misc_model
from ..models import reports as rep_model
from ..models import users as user_model
from ..services import attendance_service, evaluation_service

bp = Blueprint("teacher", __name__)


def _scope():
    """管理员看全部（None），导师看自己名下。"""
    u = security.current_user()
    return None if u["role"] == "admin" else u["id"]


def _guard_student(sid: int):
    """校验该学生是否在当前用户管辖范围内。"""
    u = security.current_user()
    stu = user_model.by_id(sid)
    if not stu or stu["role"] != "student":
        abort(404)
    if u["role"] == "teacher" and stu["advisor_id"] != u["id"]:
        abort(403)
    return stu


@bp.before_request
@security.login_required
@security.role_required("admin", "teacher")
def _guard():
    return None


@bp.route("/dashboard")
def dashboard():
    scope = _scope()
    cm = R.month_key()

    students = user_model.all_students(scope)
    no_report = rep_model.missing_this_week(scope, R.week_key())
    no_checkin = att_model.today_missing(scope, date.today().isoformat())

    overview = []
    for s in students:
        overview.append(
            {
                "u": s,
                "att_score": attendance_service.month_score(s["id"], cm),
                "has_report": s not in no_report,
                "checked_in": s not in no_checkin,
            }
        )

    evals = evaluation_service.list_evals(cm)

    return render_template(
        "teacher/dashboard.html",
        no_report=no_report,
        no_checkin=no_checkin,
        pending_leaves=misc_model.pending_leaves(scope),
        overview=overview,
        evaluated=sum(1 for s in students if s["id"] in evals),
        total_students=len(students),
        active="dashboard",
    )


@bp.route("/students/<int:sid>")
def student_detail(sid):
    stu = _guard_student(sid)
    cm = R.month_key()
    return render_template(
        "teacher/student_detail.html",
        stu=stu,
        att=attendance_service.month_detail(sid, cm),
        reports=rep_model.recent(sid),
        eval_row=evaluation_service.get_eval(sid, cm),
        leaves=misc_model.recent_leaves(sid),
        active="dashboard",
    )


@bp.route("/students/<int:sid>/comment", methods=["POST"])
def comment(sid):
    _guard_student(sid)
    rid = request.form.get("report_id", type=int)
    text = request.form.get("comment", "").strip()
    if not rid:
        abort(400)
    rep_model.set_comment(rid, sid, text)
    security.audit("report_comment", target=f"report:{rid}", detail=text[:100])
    security.get_db_commit()
    flash("评语已保存", "success")
    return redirect(url_for("teacher.student_detail", sid=sid))


@bp.route("/leaves/<int:lid>/<action>", methods=["POST"])
def leave_action(lid, action):
    if action not in ("approve", "reject"):
        abort(400)
    lv = misc_model.leave_by_id(lid)
    if not lv:
        abort(404)
    _guard_student(lv["user_id"])

    u = security.current_user()
    misc_model.set_leave_status(lid, "approved" if action == "approve" else "rejected", u["id"])
    security.audit(f"leave_{action}", target=f"leave:{lid}")
    security.get_db_commit()
    flash("已同意" if action == "approve" else "已驳回", "success")
    return redirect(request.referrer or url_for("teacher.dashboard"))


# ---------------------------------------------------------------- 考评
@bp.route("/evaluation")
def evaluation():
    scope = _scope()
    mk = _norm_month(request.args.get("month"))
    students = user_model.all_students(scope)
    evals = evaluation_service.list_evals(mk)

    rows = []
    for s in students:
        rows.append(
            {
                "u": s,
                "att": attendance_service.month_detail(s["id"], mk),
                "ev": evals.get(s["id"]),
                "n_reports": len(rep_model.month_reports(s["id"], mk[:4])),
            }
        )

    return render_template(
        "teacher/evaluation.html",
        rows=rows, mk=mk, active="evaluation",
        bands=R.BANDS, rule_version=R.RULE_VERSION, rule_source=R.RULE_SOURCE,
    )


@bp.route("/evaluation/compute", methods=["POST"])
def evaluation_compute():
    scope = _scope()
    mk = _norm_month(request.form.get("month"))
    results = evaluation_service.compute_month(mk, scope)
    security.audit(
        "evaluation_compute",
        target=f"month:{mk}",
        detail=f"{len(results)} students, rule={R.RULE_VERSION}",
    )
    security.get_db_commit()
    if not results:
        flash("没有学生可考评", "error")
    else:
        flash(f"{mk} 考评已生成（{len(results)} 人，规则 {R.RULE_VERSION}）", "success")
    return redirect(url_for("teacher.evaluation", month=mk))


@bp.route("/evaluation/<int:sid>/enable", methods=["POST"])
def evaluation_enable(sid):
    _guard_student(sid)
    mk = _norm_month(request.form.get("month"))
    try:
        score = max(0.0, min(500.0, float(request.form.get("enable_score", "0") or 0)))
    except ValueError:
        score = 0.0
    evaluation_service.set_enable_score(sid, mk, score)
    security.audit("evaluation_enable", target=f"user:{sid}", detail=f"{mk} score={score}")
    security.get_db_commit()
    flash("学术赋能分已更新，请重新生成考评", "success")
    return redirect(url_for("teacher.evaluation", month=mk))


# ---------------------------------------------------------------- 值日
@bp.route("/duty")
def duty():
    scope = _scope()
    monday = R.week_monday()
    wk_arg = request.args.get("week")
    if wk_arg:
        try:
            y, w = wk_arg.split("-W")
            monday = date.fromisocalendar(int(y), int(w), 1)
        except (ValueError, AttributeError):
            monday = R.week_monday()
    wk = R.week_key(monday)

    rows = misc_model.week_duty(
        monday.isoformat(), (monday + timedelta(days=6)).isoformat()
    )
    by_day: dict[str, list] = {}
    for r in rows:
        by_day.setdefault(r["date"], []).append(r)

    days = [{"date": monday + timedelta(days=i),
             "rows": by_day.get((monday + timedelta(days=i)).isoformat(), [])}
            for i in range(5)]

    return render_template(
        "teacher/duty.html", days=days, wk=wk,
        students=user_model.all_students(scope), active="duty",
        prev_week=R.week_key(monday - timedelta(days=7)),
        next_week=R.week_key(monday + timedelta(days=7)),
    )


@bp.route("/duty/mark", methods=["POST"])
def duty_mark():
    did = request.form.get("duty_id", type=int)
    done = 1 if request.form.get("done") == "1" else 0
    if not did:
        abort(400)
    misc_model.mark(did, done, request.form.get("note", "").strip())
    security.audit("duty_mark", target=f"duty:{did}", detail=f"done={done}")
    security.get_db_commit()
    return redirect(request.referrer or url_for("teacher.duty"))


@bp.route("/duty/assign", methods=["POST"])
def duty_assign():
    day = request.form.get("date", "")
    uid = request.form.get("user_id", type=int)
    if not day or not uid:
        abort(400)
    _guard_student(uid)
    misc_model.assign(day, uid)
    security.audit("duty_assign", target=f"duty:{day}", detail=f"user={uid}")
    security.get_db_commit()
    return redirect(request.referrer or url_for("teacher.duty"))


@bp.route("/duty/remove", methods=["POST"])
def duty_remove():
    did = request.form.get("duty_id", type=int)
    if not did:
        abort(400)
    misc_model.remove(did)
    security.audit("duty_remove", target=f"duty:{did}")
    security.get_db_commit()
    return redirect(request.referrer or url_for("teacher.duty"))


def _norm_month(mk: str | None) -> str:
    if not mk:
        return R.month_key()
    try:
        y, m = mk.split("-")
        int(y), int(m)
        return mk
    except (ValueError, AttributeError):
        return R.month_key()
