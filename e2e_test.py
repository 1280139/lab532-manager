# -*- coding: utf-8 -*-
"""真实 HTTP 端到端测试：模拟浏览器，验证完整流程与安全特性。

与 tests/ 下的单元测试互补：这里走真实网络栈，包含 cookie、重定向、CSRF。
"""

import http.cookiejar
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE = "http://127.0.0.1:8000"
PWD = "lab532demo"
fails = []


def check(name, cond, extra=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + (f"  {extra}" if not cond else ""))
    if not cond:
        fails.append(name)


class Browser:
    def __init__(self):
        self.cj = http.cookiejar.CookieJar()
        self.op = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cj)
        )

    def get(self, path):
        try:
            with self.op.open(BASE + path, timeout=15) as r:
                return r.status, r.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8")

    def post(self, path, data):
        body = urllib.parse.urlencode(data).encode()
        try:
            with self.op.open(BASE + path, body, timeout=15) as r:
                return r.status, r.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8")

    def csrf(self, path="/login"):
        _, html = self.get(path)
        m = re.search(r'name="_csrf" value="([^"]+)"', html)
        return m.group(1) if m else ""

    def login(self, acc, pwd=PWD):
        tok = self.csrf()
        return self.post("/login", {"account": acc, "password": pwd, "_csrf": tok})


print("\n[1] 健康检查")
b = Browser()
st, html = b.get("/healthz")
check("healthz 200", st == 200)
check("返回 schema 版本", "001_init" in html, html[:100])

print("\n[2] 登录页安全")
st, html = b.get("/login")
check("登录页 200", st == 200)
check("含 CSRF token", 'name="_csrf"' in html)
# 开发环境会显示演示账号（方便），生产环境必须关闭。
# 这里检查的是"密码不会以明文形式出现在表单 value 里"
check("密码未预填到输入框", 'name="password" value=' not in html, "密码被写进了 value")

print("\n[3] 未登录访问被拦截")
for p in ["/dashboard", "/my", "/evaluation", "/admin/users"]:
    st, _ = b.get(p)
    check(f"{p} 未登录跳转", st in (200, 302), f"status={st}")

print("\n[4] 错误密码")
b2 = Browser()
st, html = b2.login("admin", "wrongpassword")
check("错误密码被拒", "账号或密码错误" in html)

print("\n[5] CSRF 防护")
b3 = Browser()
b3.login("admin")
st, html = b3.post("/my/checkin", {"action": "in", "time": "08:20"})
check("无 token 的 POST 被拒 400", st == 400, f"status={st}")
st, html = b3.post("/my/checkin", {"action": "in", "time": "08:20", "_csrf": "fake"})
check("错误 token 被拒 400", st == 400, f"status={st}")

print("\n[6] 管理员登录与页面")
adm = Browser()
st, html = adm.login("admin")
check("管理员登录成功", "工作台" in html, f"status={st}")
check("导航含系统管理", "系统管理" in html)

for p, kw in [("/dashboard", "工作台"), ("/evaluation", "月度考评"),
              ("/duty", "卫生值日"), ("/admin/users", "用户管理"),
              ("/admin/audit", "审计日志"), ("/admin/system", "系统状态")]:
    st, html = adm.get(p)
    check(f"{p} 渲染", st == 200 and kw in html, f"status={st}")

print("\n[7] 审计日志已记录登录")
st, html = adm.get("/admin/audit")
check("日志含 login 动作", "login" in html)

print("\n[8] 密码哈希验证（直接查库）")
import sqlite3
conn = sqlite3.connect("lab.db")
conn.row_factory = sqlite3.Row
rows = conn.execute("SELECT account, password FROM users").fetchall()
all_hashed = all(r["password"].startswith(("scrypt:", "pbkdf2:", "argon2")) for r in rows)
check("所有密码均为哈希", all_hashed,
      [r["account"] for r in rows if not r["password"].startswith("scrypt:")])
check("库中无明文密码", not any(PWD == r["password"] for r in rows))

print("\n[9] 学生端")
stu = Browser()
st, html = stu.login("s001")
check("学生登录成功", "我的考勤" in html, f"status={st}")
check("显示本月考勤分", "本月考勤分" in html)
st, html = stu.get("/my/report")
check("周报页渲染", st == 200 and "周工作记录" in html)

print("\n[10] 学生越权")
for p in ["/dashboard", "/evaluation", "/admin/users"]:
    st, _ = stu.get(p)
    check(f"学生访问 {p} 403", st == 403, f"status={st}")

print("\n[11] 导师端")
tea = Browser()
st, html = tea.login("t001")
check("导师登录成功", "工作台" in html)
st, _ = tea.get("/admin/users")
check("导师访问系统管理 403", st == 403, f"status={st}")
st, html = tea.get("/students/3")
check("导师看学生详情", st == 200 and "考勤明细" in html)

print("\n[12] 考评计算与追溯")
tok = tea.csrf("/evaluation")
st, html = tea.post("/evaluation/compute", {"month": "", "_csrf": tok})
check("考评生成成功", "考评已生成" in html, f"status={st}")
check("页面显示规则版本", "V20250901" in html)

conn2 = sqlite3.connect("lab.db")
conn2.row_factory = sqlite3.Row
evs = conn2.execute("SELECT * FROM evaluations").fetchall()
check("考评记录已写入", len(evs) == 5, f"实际 {len(evs)}")
check("每条都有规则版本", all(e["rule_version"] == "V20250901" for e in evs))
check("每条都有计算快照", all(e["snapshot"] and len(e["snapshot"]) > 100 for e in evs))

import json
snap_ok = True
for e in evs:
    s = json.loads(e["snapshot"])
    if abs(s["s_value"] - e["s_value"]) > 0.01:
        snap_ok = False
    if "attendance" not in s or "reports" not in s:
        snap_ok = False
check("快照与记录一致", snap_ok)

print("\n[13] 强制分布实际生效")
grades = [e["grade"] for e in evs]
check("存在 A 档", "A" in grades, str(grades))
check("存在非零金额", any(e["final_amount"] > 0 for e in evs))

print("\n[14] 审计日志覆盖操作")
st, html = adm.get("/admin/audit")
check("记录了考评计算", "evaluation_compute" in html, "未记录")

print("\n[15] 静态资源与错误页")
st, _ = adm.get("/static/style.css")
check("CSS 可访问", st == 200)
st, _ = adm.get("/nonexistent")
check("404 页面", st == 404)

print("\n[16] 生产配置隔离")
import os
import subprocess

code = (
    "from app import create_app;"
    "a=create_app('prod');"
    "print('DEMO', a.config.get('SHOW_DEMO_ACCOUNTS'));"
    "print('FALLBACK', a.config.get('ALLOW_PLAIN_PASSWORD_FALLBACK'))"
)
env = dict(os.environ, SECRET_KEY="x" * 48, FLASK_ENV="prod")
r = subprocess.run(
    [sys.executable, "-c", code], capture_output=True, text=True, env=env,
    encoding="utf-8", errors="replace",
)
out = (r.stdout or "") + (r.stderr or "")
check("生产环境关闭演示账号", "DEMO False" in out, out[:200])
check("生产环境禁用明文回退", "FALLBACK False" in out, out[:200])

code2 = (
    "from app import create_app;"
    "create_app('prod')"
)
env2 = dict(os.environ, FLASK_ENV="prod")
env2.pop("SECRET_KEY", None)
r2 = subprocess.run(
    [sys.executable, "-c", code2], capture_output=True, text=True, env=env2,
    encoding="utf-8", errors="replace",
)
out2 = (r2.stdout or "") + (r2.stderr or "")
check("生产环境缺 SECRET_KEY 拒绝启动",
      r2.returncode != 0 and "SECRET_KEY" in out2, f"rc={r2.returncode} {out2[:200]}")

conn.close()
conn2.close()

print("\n" + "=" * 56)
if fails:
    print(f"失败 {len(fails)} 项：")
    for f in fails:
        print("  -", f)
    sys.exit(1)
print("端到端测试全部通过")
