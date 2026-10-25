# -*- coding: utf-8 -*-
"""应用工厂。"""

from __future__ import annotations

import os

from flask import Flask, jsonify, redirect, render_template, url_for

from . import db, security
from .config import get_config


def create_app(config_name: str | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=False)

    cfg = get_config(config_name)
    app.config.from_object(cfg)
    if not isinstance(cfg, type):
        app.config["DB_PATH"] = cfg.DB_PATH

    os.makedirs(app.config["DATA_DIR"], exist_ok=True)

    db.init_app(app)
    security.init_app(app)

    # 蓝图
    from .views import admin, auth, student, teacher

    app.register_blueprint(auth.bp)
    app.register_blueprint(student.bp)
    app.register_blueprint(teacher.bp)
    app.register_blueprint(admin.bp)

    # 模板过滤器
    _register_filters(app)

    # 错误页
    @app.errorhandler(400)
    def _400(e):
        return render_template("error.html", code=400,
                               msg=getattr(e, "description", "请求无效")), 400

    @app.errorhandler(403)
    def _403(e):
        return render_template("error.html", code=403, msg="你没有权限访问这个页面"), 403

    @app.errorhandler(404)
    def _404(e):
        return render_template("error.html", code=404, msg="页面不存在"), 404

    @app.route("/")
    def index():
        u = security.current_user()
        if not u:
            return redirect(url_for("auth.login"))
        if u["role"] in ("admin", "teacher"):
            return redirect(url_for("teacher.dashboard"))
        return redirect(url_for("student.home"))

    @app.route("/healthz")
    def healthz():
        try:
            db.get_db().execute("SELECT 1").fetchone()
            return jsonify(
                status="ok",
                db=os.path.basename(app.config["DB_PATH"]),
                schema=db.current_version(db.get_db()),
            )
        except Exception as e:  # noqa: BLE001
            return jsonify(status="error", detail=str(e)), 500

    return app


def _register_filters(app: Flask) -> None:
    from datetime import date, datetime

    from . import rules as R

    def _as_date(s):
        if isinstance(s, datetime):
            return s.date()
        if isinstance(s, date):
            return s
        try:
            return date.fromisoformat(str(s)[:10])
        except (ValueError, TypeError):
            return None

    @app.template_filter("short_date")
    def short_date(s):
        d = _as_date(s)
        return f"{d.month:02d}-{d.day:02d}" if d else ""

    @app.template_filter("weekday_cn")
    def weekday_cn(s):
        d = _as_date(s)
        return R.WEEKDAY_CN[d.weekday()] if d else ""

    @app.template_filter("long_date")
    def long_date(s):
        d = _as_date(s)
        if not d:
            return s or ""
        return f"{d.year} 年 {d.month} 月 {d.day} 日 {R.WEEKDAY_CN[d.weekday()]}"

    @app.template_filter("money")
    def money(v):
        try:
            return f"{float(v):,.0f}"
        except (TypeError, ValueError):
            return "—"

    @app.template_filter("pct")
    def pct(v):
        try:
            return f"{float(v) * 100:.0f}%"
        except (TypeError, ValueError):
            return "—"

    @app.context_processor
    def _globals():
        u = security.current_user()
        return {
            "user": u,
            "today_str": date.today().isoformat(),
            "today_date": date.today(),
            "current_week": R.week_key(),
            "current_month": R.month_key(),
            "rule_version": R.RULE_VERSION,
            "rule_source": R.RULE_SOURCE,
            "week_label": lambda wk: _week_label(wk),
            "week_range_label": lambda wk: _week_range(wk),
            "month_label": lambda mk: _month_label(mk),
            "ROLE_CN": {"admin": "管理员", "teacher": "导师", "student": "学生"},
            "DEGREE_CN": {"phd": "博士", "master": "硕士"},
            "ASSIST_CN": {"I": "I 类助研", "II": "II 类助研"},
            "STATUS_CN": R.STATUS_CN,
            "WEEKDAY_CN": R.WEEKDAY_CN,
        }


def _week_label(wk: str) -> str:
    y, w = wk.split("-W")
    return f"{y} 年第 {int(w)} 周"


def _week_range(wk: str) -> str:
    from datetime import date, timedelta

    y, w = wk.split("-W")
    mon = date.fromisocalendar(int(y), int(w), 1)
    sun = mon + timedelta(days=6)
    return f"{mon.month}/{mon.day} - {sun.month}/{sun.day}"


def _month_label(mk: str) -> str:
    y, m = mk.split("-")
    return f"{y} 年 {int(m)} 月"
