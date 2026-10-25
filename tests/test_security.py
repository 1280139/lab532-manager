# -*- coding: utf-8 -*-
"""安全专项测试：验证密码哈希、CSRF、权限隔离确实生效。

这些是 v1 缺失的部分，也是最容易"看起来有、实际没有"的地方。
"""

import sqlite3

import pytest

from app.security import hash_password, is_hashed, verify_password
from tests.conftest import csrf_of, login, post


class TestPasswordHashing:
    def test_hash_is_not_plaintext(self):
        h = hash_password("mypassword123")
        assert h != "mypassword123"
        assert is_hashed(h)
        assert h.startswith("scrypt:")

    def test_verify_correct(self):
        h = hash_password("mypassword123")
        ok, upgrade = verify_password(h, "mypassword123")
        assert ok
        assert not upgrade

    def test_verify_wrong(self):
        h = hash_password("mypassword123")
        ok, _ = verify_password(h, "wrongpassword")
        assert not ok

    def test_same_password_different_hash(self):
        """加盐：同样的密码两次哈希结果不同。"""
        assert hash_password("abc") != hash_password("abc")

    def test_seed_passwords_are_hashed(self, app):
        """种子数据里的密码必须是哈希，不能有明文。"""
        with app.app_context():
            from app.db import get_db

            rows = get_db().execute("SELECT account, password FROM users").fetchall()
            assert len(rows) > 0
            for r in rows:
                assert is_hashed(r["password"]), f"{r['account']} 的密码是明文！"
                assert "lab532demo" not in r["password"]


class TestCSRF:
    def test_post_without_token_rejected(self, client):
        client.post("/login", data={"account": "admin", "password": "lab532demo"})
        r = client.post("/my/checkin", data={"action": "in", "time": "08:20"})
        assert r.status_code == 400

    def test_post_with_wrong_token_rejected(self, client):
        login(client)
        r = client.post(
            "/my/checkin",
            data={"action": "in", "time": "08:20", "_csrf": "wrong-token"},
        )
        assert r.status_code == 400

    def test_post_with_valid_token_accepted(self, client):
        login(client, "s001")
        r = post(client, "/my/checkin", {"action": "in", "time": "08:20"})
        assert r.status_code == 200

    def test_login_form_has_token(self, client):
        html = client.get("/login").get_data(as_text=True)
        assert 'name="_csrf"' in html

    def test_all_post_forms_have_csrf(self, client):
        """逐个页面检查，确保没有漏掉的表单。"""
        import re

        login(client, "admin")
        pages = ["/dashboard", "/evaluation", "/duty", "/admin/users", "/my/report"]
        for p in pages:
            html = client.get(p).get_data(as_text=True)
            forms = re.findall(
                r"<form[^>]*method=\"post\"[^>]*>(.*?)</form>", html, flags=re.S | re.I
            )
            for f in forms:
                assert "_csrf" in f, f"{p} 有表单缺 CSRF"


class TestLoginFlow:
    def test_wrong_password(self, client):
        tok = csrf_of(client)
        r = client.post(
            "/login",
            data={"account": "admin", "password": "wrong", "_csrf": tok},
            follow_redirects=True,
        )
        assert "账号或密码错误" in r.get_data(as_text=True)

    def test_correct_password(self, client):
        r = login(client, "admin")
        assert "工作台" in r.get_data(as_text=True)

    def test_nonexistent_account(self, client):
        tok = csrf_of(client)
        r = client.post(
            "/login",
            data={"account": "nobody", "password": "x", "_csrf": tok},
            follow_redirects=True,
        )
        assert "账号或密码错误" in r.get_data(as_text=True)

    def test_logout_clears_session(self, client):
        login(client)
        client.get("/logout")
        r = client.get("/dashboard")
        assert r.status_code == 302  # 跳回登录

    def test_session_timeout_configured(self, app):
        assert app.config["PERMANENT_SESSION_LIFETIME"].total_seconds() == 8 * 3600

    def test_cookie_flags(self, app):
        assert app.config["SESSION_COOKIE_HTTPONLY"] is True
        assert app.config["SESSION_COOKIE_SAMESITE"] == "Lax"


class TestPlaintextUpgrade:
    def test_legacy_plaintext_upgraded_on_login(self, app, client):
        """旧库里的明文密码，首次登录后应自动升级为哈希。"""
        with app.app_context():
            from app.db import get_db

            db = get_db()
            db.execute("UPDATE users SET password='plaintext123' WHERE account='s002'")
            db.commit()

        tok = csrf_of(client)
        r = client.post(
            "/login",
            data={"account": "s002", "password": "plaintext123", "_csrf": tok},
            follow_redirects=True,
        )
        assert r.status_code == 200

        with app.app_context():
            from app.db import get_db

            pw = get_db().execute(
                "SELECT password FROM users WHERE account='s002'"
            ).fetchone()["password"]
            assert is_hashed(pw), "明文密码没有被升级为哈希"
            assert pw != "plaintext123"


class TestPermission:
    def test_student_cannot_access_dashboard(self, client):
        login(client, "s001")
        assert client.get("/dashboard").status_code == 403

    def test_student_cannot_access_evaluation(self, client):
        login(client, "s001")
        assert client.get("/evaluation").status_code == 403

    def test_student_cannot_access_admin(self, client):
        login(client, "s001")
        assert client.get("/admin/users").status_code == 403

    def test_teacher_cannot_access_admin(self, client):
        login(client, "t001")
        assert client.get("/admin/users").status_code == 403

    def test_teacher_cannot_see_other_students(self, app, client):
        with app.app_context():
            from app.db import get_db

            db = get_db()
            db.execute(
                """INSERT INTO users(name,account,password,role,advisor_id)
                   VALUES('外人','x999',?,'student',NULL)""",
                (hash_password("x"),),
            )
            db.commit()
            outsider = db.execute(
                "SELECT id FROM users WHERE account='x999'"
            ).fetchone()["id"]

        login(client, "t001")
        assert client.get(f"/students/{outsider}").status_code == 403

    def test_admin_can_see_all(self, client):
        login(client, "admin")
        r = client.get("/students/3")
        assert r.status_code == 200

    def test_unauthenticated_redirected(self, client):
        r = client.get("/dashboard")
        assert r.status_code == 302
        assert "/login" in r.headers["Location"]


class TestAuditLog:
    def test_login_is_logged(self, app, client):
        login(client, "admin")
        with app.app_context():
            from app.db import get_db

            row = get_db().execute(
                "SELECT * FROM audit_log WHERE action='login'"
            ).fetchone()
            assert row is not None
            assert row["ip"] is not None

    def test_checkin_is_logged(self, app, client):
        """打卡成功时写审计日志。周末会被正确拦截，故需跳过。"""
        from datetime import date

        if date.today().weekday() >= 5:
            pytest.skip("今天是周末，打卡被规则拦截，无法验证审计日志")

        login(client, "s001")
        post(client, "/my/checkin", {"action": "in", "time": "08:20"})
        with app.app_context():
            from app.db import get_db

            row = get_db().execute(
                "SELECT * FROM audit_log WHERE action='checkin'"
            ).fetchone()
            assert row is not None
            assert "08:20" in row["detail"]

    def test_weekend_checkin_rejected(self, app, client):
        """周末打卡必须被拒绝，且不产生打卡记录。"""
        from datetime import date

        if date.today().weekday() < 5:
            pytest.skip("今天是工作日，无法验证周末拦截")

        login(client, "s001")
        r = post(client, "/my/checkin", {"action": "in", "time": "08:20"})
        assert "周末不考勤" in r.get_data(as_text=True)

    def test_password_change_logged(self, app, client):
        login(client, "s001")
        post(client, "/password", {
            "old": "lab532demo", "new": "newpassword123", "confirm": "newpassword123",
        })
        with app.app_context():
            from app.db import get_db

            row = get_db().execute(
                "SELECT * FROM audit_log WHERE action='change_password'"
            ).fetchone()
            assert row is not None


class TestDBConstraints:
    def test_unique_attendance(self, app):
        with app.app_context():
            from app.db import get_db

            db = get_db()
            uid = db.execute("SELECT id FROM users WHERE account='s001'").fetchone()["id"]
            db.execute("DELETE FROM attendance WHERE user_id=? AND date='2020-01-02'", (uid,))
            db.execute(
                "INSERT INTO attendance(user_id,date,check_in,created_at) VALUES(?,?,?,?)",
                (uid, "2020-01-02", "08:00", "2020-01-02 08:00:00"),
            )
            db.commit()
            with pytest.raises(sqlite3.IntegrityError):
                db.execute(
                    "INSERT INTO attendance(user_id,date,check_in,created_at) VALUES(?,?,?,?)",
                    (uid, "2020-01-02", "09:00", "2020-01-02 09:00:00"),
                )

    def test_role_check(self, app):
        with app.app_context():
            from app.db import get_db

            db = get_db()
            with pytest.raises(sqlite3.IntegrityError):
                db.execute(
                    "INSERT INTO users(name,account,password,role) VALUES('x','xx1','h','hacker')"
                )

    def test_foreign_key_enforced(self, app):
        with app.app_context():
            from app.db import get_db

            db = get_db()
            with pytest.raises(sqlite3.IntegrityError):
                db.execute(
                    "INSERT INTO attendance(user_id,date,created_at) VALUES(99999,'2020-01-01','x')"
                )
