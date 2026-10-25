# -*- coding: utf-8 -*-
"""业务流程与追溯性测试：考评计算、规则版本、快照。"""

import json
from datetime import date

import pytest

from app import rules as R
from app.services import evaluation_service
from tests.conftest import login, post


class TestEvaluationCompute:
    def test_compute_produces_records(self, app):
        with app.app_context():
            from app.db import get_db

            results = evaluation_service.compute_month(R.month_key(), None)
            assert len(results) == 5
            rows = get_db().execute(
                "SELECT * FROM evaluations WHERE month_key=?", (R.month_key(),)
            ).fetchall()
            assert len(rows) == 5

    def test_zero_report_gets_zero_task_score(self, app):
        """本月零周报者，任务分必须是 0（手册明确规定）。"""
        with app.app_context():
            from app.db import get_db

            db = get_db()
            # 清空某学生本月周报
            uid = db.execute("SELECT id FROM users WHERE account='s003'").fetchone()["id"]
            db.execute("DELETE FROM reports WHERE user_id=?", (uid,))
            db.commit()

            results = evaluation_service.compute_month(R.month_key(), None)
            target = [r for r in results if r["student"]["id"] == uid][0]
            assert target["task_score"] == 0.0
            assert "未提交周报" in target["note"]

    def test_zero_report_not_in_ranking(self, app):
        """零周报者不参与强制分布，不挤占他人名额。"""
        with app.app_context():
            from app.db import get_db

            db = get_db()
            uid = db.execute("SELECT id FROM users WHERE account='s003'").fetchone()["id"]
            db.execute("DELETE FROM reports WHERE user_id=?", (uid,))
            db.commit()

            results = evaluation_service.compute_month(R.month_key(), None)
            eligible = [r for r in results if r["student"]["id"] != uid]
            buckets = [r["bucket"] for r in eligible]
            # 4 人按 10/20/30/40 -> 0/1/1/2
            assert buckets.count("优秀") == 0
            assert buckets.count("良好") == 1
            assert buckets.count("中等") == 1
            assert buckets.count("合格") == 2

    def test_rule_version_recorded(self, app):
        """每条考评必须写明规则版本。"""
        with app.app_context():
            from app.db import get_db

            evaluation_service.compute_month(R.month_key(), None)
            rows = get_db().execute("SELECT * FROM evaluations").fetchall()
            for r in rows:
                assert r["rule_version"] == R.RULE_VERSION

    def test_snapshot_saved(self, app):
        """计算快照必须保存，且内容完整。"""
        with app.app_context():
            from app.db import get_db

            evaluation_service.compute_month(R.month_key(), None)
            row = get_db().execute("SELECT * FROM evaluations LIMIT 1").fetchone()
            assert row["snapshot"]
            snap = json.loads(row["snapshot"])
            assert "rule_version" in snap
            assert "attendance" in snap
            assert "reports" in snap
            assert "formula" in snap
            assert snap["attendance"]["score"] == row["attendance_score"]

    def test_snapshot_reproducible(self, app):
        """快照里的分数必须与库中记录一致，保证可复现。"""
        with app.app_context():
            from app.db import get_db

            evaluation_service.compute_month(R.month_key(), None)
            rows = get_db().execute("SELECT * FROM evaluations").fetchall()
            for r in rows:
                snap = json.loads(r["snapshot"])
                assert snap["s_value"] == r["s_value"]
                assert snap["final_amount"] == r["final_amount"]
                assert snap["grade"] == r["grade"]

    def test_attendance_score_matches_service(self, app):
        with app.app_context():
            from app.db import get_db
            from app.services import attendance_service

            evaluation_service.compute_month(R.month_key(), None)
            rows = get_db().execute("SELECT * FROM evaluations").fetchall()
            for r in rows:
                expected = attendance_service.month_score(r["user_id"], r["month_key"])
                assert abs(r["attendance_score"] - expected) < 0.01

    def test_recompute_updates_not_duplicates(self, app):
        with app.app_context():
            from app.db import get_db

            evaluation_service.compute_month(R.month_key(), None)
            n1 = get_db().execute("SELECT COUNT(*) c FROM evaluations").fetchone()["c"]
            evaluation_service.compute_month(R.month_key(), None)
            n2 = get_db().execute("SELECT COUNT(*) c FROM evaluations").fetchone()["c"]
            assert n1 == n2, "重复生成考评不应产生重复记录"


class TestAttendanceService:
    def test_start_date_excludes_early_month(self, app):
        """起算日 = 本月第一条记录，之前的日期不算缺勤。"""
        with app.app_context():
            from app.services import attendance_service

            uid = _uid(app, "s001")
            detail = attendance_service.month_detail(uid, R.month_key())
            if detail["start_date"]:
                first_record = min(
                    d["date"] for d in detail["days"] if d["row"] is not None
                ) if detail["days"] else None
                assert detail["start_date"] <= first_record if first_record else True

    def test_no_data_returns_full_score(self, app):
        """整月无记录 -> 100 分，而不是把全月算成缺勤。"""
        with app.app_context():
            from app.services import attendance_service

            uid = _uid(app, "s002")
            detail = attendance_service.month_detail(uid, "2019-01")
            assert detail["score"] == 100.0
            assert detail["total_deduction"] == 0


class TestStudentFlows:
    def test_checkin_records(self, client, app):
        login(client, "s001")
        r = post(client, "/my/checkin", {"action": "in", "time": "08:20"})
        assert r.status_code == 200

    def test_report_validation_blocks_short(self, client):
        login(client, "s001")
        r = post(client, "/my/report", {
            "周一": "短", "周二": "", "周三": "", "周四": "", "周五": "",
            "summary": "x", "next_plan": "y",
        })
        assert "未填写" in r.get_data(as_text=True) or "不足" in r.get_data(as_text=True)

    def test_report_submit_success(self, client):
        login(client, "s001")
        long_text = "上午精读论文两节并整理公式推导，下午跑对比实验记录显存占用，晚上复盘数据。"
        r = post(client, "/my/report", {
            "周一": long_text, "周二": long_text, "周三": long_text,
            "周四": long_text, "周五": long_text,
            "summary": "本周完成 baseline 复现第一阶段，跑通两组对比实验。",
            "next_plan": "下周完成剩余消融实验并整理成表。",
        })
        assert "已提交" in r.get_data(as_text=True)

    def test_leave_requires_advance_day(self, client):
        login(client, "s001")
        r = post(client, "/my/leave", {
            "date": date.today().isoformat(), "kind": "sick", "half": "full",
        })
        assert "提前 1 天" in r.get_data(as_text=True)


class TestTeacherFlows:
    def test_dashboard_loads(self, client):
        login(client, "t001")
        r = client.get("/dashboard")
        assert r.status_code == 200
        assert "工作台" in r.get_data(as_text=True)

    def test_student_detail_loads(self, client):
        login(client, "t001")
        r = client.get("/students/3")
        assert r.status_code == 200

    def test_evaluation_page_shows_rule_version(self, client):
        login(client, "t001")
        r = client.get("/evaluation")
        assert R.RULE_VERSION in r.get_data(as_text=True)

    def test_comment_saved(self, client, app):
        login(client, "t001")
        with app.app_context():
            from app.db import get_db

            rid = get_db().execute("SELECT id FROM reports LIMIT 1").fetchone()["id"]
        r = post(client, "/students/3/comment", {"report_id": rid, "comment": "测试评语"})
        assert "测试评语" in r.get_data(as_text=True)


class TestAdminFlows:
    def test_admin_pages_load(self, client):
        login(client, "admin")
        for p in ["/admin/users", "/admin/audit", "/admin/system"]:
            assert client.get(p).status_code == 200, p

    def test_create_user_hashes_password(self, client, app):
        login(client, "admin")
        post(client, "/admin/users/create", {
            "name": "测试学生", "account": "test001", "password": "testpass123",
            "role": "student", "degree": "master", "assist_type": "I", "grade": "2026",
        })
        with app.app_context():
            from app.db import get_db
            from app.security import is_hashed

            pw = get_db().execute(
                "SELECT password FROM users WHERE account='test001'"
            ).fetchone()["password"]
            assert is_hashed(pw)
            assert pw != "testpass123"

    def test_export_returns_sqlite(self, client):
        login(client, "admin")
        r = client.get("/admin/export")
        assert r.status_code == 200
        assert r.data[:16].startswith(b"SQLite format 3")


def _uid(app, account):
    with app.app_context():
        from app.db import get_db

        return get_db().execute(
            "SELECT id FROM users WHERE account=?", (account,)
        ).fetchone()["id"]
