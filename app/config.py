# -*- coding: utf-8 -*-
"""配置分离：开发 / 测试 / 生产。

生产环境必须通过环境变量提供 SECRET_KEY，否则拒绝启动。
"""

import os
import secrets
from datetime import timedelta

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class BaseConfig:
    # 数据库目录：云平台挂载持久磁盘时用 DATA_DIR 指向它
    DATA_DIR = os.environ.get("DATA_DIR", BASE_DIR)
    DB_NAME = "lab.db"
    DB_PATH = os.path.join(DATA_DIR, DB_NAME)

    # 是否在登录页展示演示账号与密码。生产环境必须关闭。
    SHOW_DEMO_ACCOUNTS = False

    # 会话
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.environ.get("HTTPS_ONLY") == "1"
    # Flask 要求 timedelta；直接给 int 不会自动转换，会导致会话永不过期
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)

    # CSRF
    WTF_CSRF_TIME_LIMIT = timedelta(hours=4)

    # 分页
    PAGE_SIZE = 20


class DevConfig(BaseConfig):
    DEBUG = True
    SECRET_KEY = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
    # 开发期允许明文回退，方便查看种子数据
    ALLOW_PLAIN_PASSWORD_FALLBACK = True
    SHOW_DEMO_ACCOUNTS = True


class TestConfig(BaseConfig):
    TESTING = True
    DEBUG = False
    SECRET_KEY = "test-secret-key-fixed"
    DATA_DIR = os.environ.get("TEST_DATA_DIR", os.path.join(BASE_DIR, ".test_data"))
    DB_PATH = os.path.join(DATA_DIR, "test.db")
    ALLOW_PLAIN_PASSWORD_FALLBACK = True


class ProdConfig(BaseConfig):
    DEBUG = False
    ALLOW_PLAIN_PASSWORD_FALLBACK = False

    def __init__(self):
        key = os.environ.get("SECRET_KEY")
        if not key or len(key) < 32:
            raise RuntimeError(
                "生产环境必须设置 SECRET_KEY（至少 32 字符）。\n"
                "生成方式：python -c \"import secrets; print(secrets.token_hex(32))\""
            )
        self.SECRET_KEY = key


CONFIGS = {
    "dev": DevConfig,
    "test": TestConfig,
    "prod": ProdConfig,
}


def get_config(name: str | None = None):
    name = name or os.environ.get("FLASK_ENV", "dev")
    cls = CONFIGS.get(name, DevConfig)
    return cls() if name == "prod" else cls
