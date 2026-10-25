# -*- coding: utf-8 -*-
"""WSGI 入口，供 waitress / gunicorn 使用。"""

import os

from app import create_app

app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    try:
        from waitress import serve

        print(f"生产模式：waitress，监听 0.0.0.0:{port}")
        serve(app, host="0.0.0.0", port=port, threads=8)
    except ImportError:
        print(f"开发模式：Flask，监听 0.0.0.0:{port}")
        app.run(host="0.0.0.0", port=port, debug=False)
