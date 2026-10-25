# 532Lab 管理系统

依据《实验室2025级新生手册 V20250901》实现的研究生管理制度系统。Flask + SQLite + Jinja2，分层架构，可部署、可追溯、可迁移。

## 为什么是 v2

v1（`../532lab/`）是单文件原型，能演示但**不能真用**：密码明文、无 CSRF、无迁移、考评不可追溯。

v2 在功能等价的前提下补齐了四层：

| 层 | v1 | v2 |
|---|---|---|
| 安全 | 明文密码、无 CSRF | scrypt 哈希、全站 CSRF、会话超时、审计日志 |
| 结构 | 1154 行单文件 | 分层：models / services / views |
| 可演进 | 无迁移 | `migrations/*.sql` + schema_version |
| 可追溯 | 考评算完即消失 | 规则版本 + 完整计算快照 |

## 快速开始

```bash
pip install -r requirements.txt
python manage.py init        # 建库 + 迁移 + 种子数据
python wsgi.py               # 启动，默认 8000 端口
```

打开 http://127.0.0.1:8000

| 账号 | 密码 | 角色 |
|---|---|---|
| `admin` | `lab532demo` | 管理员（用户管理、审计、备份） |
| `t001` | `lab532demo` | 张老师（导师） |
| `s001` | `lab532demo` | 张三（正常） |
| `s003` | `lab532demo` | 王五（问题学生） |
| `s004` | `lab532demo` | 赵六（博士） |

**演示密码只在开发环境显示**。生产环境登录页不会出现任何账号提示。

## 目录结构

```
532lab-v2/
├── app/
│   ├── __init__.py          # create_app() 工厂
│   ├── config.py            # dev / test / prod 三套配置
│   ├── db.py                # 连接管理 + 迁移执行器
│   ├── security.py          # 密码哈希、CSRF、登录态、审计
│   ├── rules.py             # 制度规则引擎（纯函数，含 RULE_VERSION）
│   ├── seed.py              # 演示数据
│   ├── models/              # 数据访问：users / attendance / reports / misc
│   ├── services/            # 业务：attendance_service / evaluation_service
│   ├── views/               # 路由：auth / student / teacher / admin
│   ├── templates/
│   └── static/
├── migrations/              # 001_init.sql ...
├── tests/                   # pytest 风格单元测试
├── manage.py                # init / migrate / create-admin / backup / status
├── wsgi.py                  # WSGI 入口
└── e2e_test.py              # 真实 HTTP 端到端测试
```

**分层原则**：`models` 只管 SQL，`services` 只管业务规则，`views` 只管 HTTP。`rules.py` 不依赖任何其他模块，可单独测试。

## 三个核心设计

### 1. 规则版本化

`rules.py` 顶部有 `RULE_VERSION = "V20250901"`。每条考评记录都写入这个版本号。

手册每年更新（如 V20260901），正确做法是**新增一套常量 + 递增版本号**，而不是改旧常量。这样历史考评仍能回答"当时按哪版规则算的"。

### 2. 计算留痕

每次生成考评，`evaluation_service.compute_month()` 会把当时的完整依据存进 `evaluations.snapshot`（JSON）：

```json
{
  "rule_version": "V20250901",
  "attendance": {
    "score": 94.0,
    "total_deduction": 6.0,
    "breakdown": {"late": {"count": 3, "points": 6.0}},
    "days": [{"date": "2026-10-12", "status": "late", "deduction": 2}, ...]
  },
  "reports": {
    "count": 2, "weeks": ["2026-W42", "2026-W43"],
    "avg_word_count": 320.0, "rank": 2, "bucket": "良好", "task_score": 79.0
  },
  "formula": "S = 考勤*0.4 + 任务*0.6 + 赋能*0.3",
  "s_value": 85.0, "grade": "A", "ratio": 1.1, "final_amount": 550.0
}
```

学生质疑"为什么只有 550 元"，直接查快照就能拿出当时每一天的打卡判定和排名依据，**不需要重新计算**（数据可能已变）。

### 3. 考勤起算日

`attendance_service.month_detail()` 从**本月第一条考勤记录**起算，不把系统上线前/制度执行前的日子算成缺勤。

这不是小细节：不加这个逻辑，10 月 1-10 日没数据会被判 10 次缺勤，扣光 100 分，所有人考勤分清零、津贴全部归零。v1 实际踩过这个坑。

## 已实现的手册规则

| 手册条款 | 实现位置 |
|---|---|
| 考勤 8:30—21:00，周末不考勤 | `rules.CHECK_IN_DEADLINE` / `is_weekend()` |
| 缺勤−10 / 旷工迟到−5 / 缺卡−5 / 严重迟到−4 / 迟到−2 / 事假−2 / 病假−1 | `rules.DEDUCT` |
| 每月考勤分初始 100 | `rules.attendance_month()` |
| 补卡 3 个工作日内、每月 3 次 | `rules.check_makeup()` |
| 请假提前 1 天、导师审批 | `views/student.py` + `views/teacher.py` |
| 周报 ≥200 字、分上午/下午/晚上、逐日填写 | `rules.check_report()` |
| 月末周报追加本月总结 | `templates/student/report.html` |
| 本月零周报 → 任务分记 0，且不参与排名 | `evaluation_service.compute_month()` |
| 任务分 10/20/30/40 强制分布 | `rules.forced_distribution()` |
| S = 考勤×40% + 任务×60% + 赋能×30% | `rules.compute_s()` |
| 等级 A/B/C/D 与发放比例，考勤<50 直接 0% | `rules.PAYOUT_RULES` |
| 博士 1000 / 硕士 I 类 200 / 硕士 II 类 500 | `rules.BASE_ALLOWANCE` |

## 测试

```bash
# 单元测试（无需启动服务）
python -m tests.minipytest        # 无 pytest 环境用这个
pytest                             # 有 pytest 时用这个

# 端到端（需先启动 wsgi.py）
python e2e_test.py
```

单元测试 81 项，端到端 40 项。覆盖：规则边界、密码哈希、CSRF、越权、审计、快照一致性、生产配置隔离。

**测试使用独立临时数据库**，不污染 `lab.db`。

## 管理命令

```bash
python manage.py init           # 初始化（迁移 + 种子数据）
python manage.py migrate        # 只跑迁移
python manage.py create-admin   # 交互式创建管理员
python manage.py backup         # 在线备份（用 SQLite backup API，保证一致性）
python manage.py status         # 查看版本与数据量
```

## 部署

### 生产环境必做

```bash
export FLASK_ENV=prod
export SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")
export DATA_DIR=/var/data       # 数据库放在持久磁盘
export HTTPS_ONLY=1             # cookie 只走 HTTPS

python manage.py migrate
python manage.py create-admin   # 不要用种子数据
python wsgi.py
```

生产配置会自动：
- 拒绝启动如果没有 `SECRET_KEY`（或长度 < 32）
- 关闭登录页的演示账号显示
- 禁用明文密码回退

### 环境变量

| 变量 | 说明 |
|---|---|
| `FLASK_ENV` | `dev` / `test` / `prod` |
| `SECRET_KEY` | **prod 必填**，至少 32 字符 |
| `DATA_DIR` | 数据库目录 |
| `HTTPS_ONLY` | 设为 `1` 时 cookie 加 Secure 标记 |
| `PORT` | 监听端口，默认 8000 |

### 备份策略

建议**每次生成月度考评后备份一次**：

```bash
python manage.py backup
```

或在系统管理页点"下载数据库备份"。备份文件是完整 SQLite，可直接打开查看或恢复。

## 规则空白（需实验室确认）

手册未明确、代码自行假设的地方，在 `rules.py` 中用 `[假设]` 标注：

1. **严重迟到阈值**——手册只说"严重迟到"，取晚于 9:30（`SEVERE_LATE_AFTER`）
2. **迟到且早退**——取较重者（严重迟到 −4）
3. **S 公式权重 130%**——理解为 40+60 构成基础分，赋能分按 30% 加权作加分
4. **补卡是否免扣分**——当前**仍按缺卡扣 5 分**。若应免扣，改 `judge_attendance` 中 `makeup` 分支
5. **考勤起算日**——见上文"三个核心设计"第 3 点

## 后续规划

Phase 1（已完成）：考勤、周报、值日、月度考评

Phase 2（待做）：
- 成果台账：论文 / 专利 / 项目 / 竞赛，按 2A/1A1B/1A 折算
- 2A 达标进度跟踪
- 津贴发放记录与导出

Phase 3（待做）：
- Seminar 排期与分享记录
- 离校交接单（物品/文件/项目三类清单）
- 年度考评汇总报表
