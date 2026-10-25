# -*- coding: utf-8 -*-
"""测试基座：每个测试模块用独立数据库，绝不污染主库。"""

from __future__ import annotations

import os
import shutil
import tempfile

import pytest

from app import create_app, db


@pytest.fixture(scope="function")
def app():
    tmpdir = tempfile.mkdtemp(prefix="532lab-test-")
    os.environ["TEST_DATA_DIR"] = tmpdir

    application = create_app("test")
    application.config["DB_PATH"] = os.path.join(tmpdir, "test.db")

    with application.app_context():
        db.migrate()
        from app.seed import seed

        seed(db.get_db())

    yield application

    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture
def client(app):
    return app.test_client()


def csrf_of(client, path="/login") -> str:
    """从页面里取 CSRF token。"""
    import re

    html = client.get(path).get_data(as_text=True)
    m = re.search(r'name="_csrf" value="([^"]+)"', html)
    assert m, f"{path} 页面没有 CSRF token"
    return m.group(1)


def login(client, account="admin", password="lab532demo"):
    tok = csrf_of(client)
    r = client.post(
        "/login",
        data={"account": account, "password": password, "_csrf": tok},
        follow_redirects=True,
    )
    return r


def post(client, path, data=None, follow=True):
    """自动带上当前 session 的 CSRF token。"""
    from flask import session

    data = dict(data or {})
    # 必须在请求上下文内取 token
    with client.session_transaction() as sess:
        tok = sess.get("_csrf_token", "")
    data.setdefault("_csrf", tok)
    return client.post(path, data=data, follow_redirects=follow)
