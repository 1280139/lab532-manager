# -*- coding: utf-8 -*-
"""532Lab 制度规则引擎 —— 纯函数，无副作用，可单独单元测试。

所有数字都可追溯到《实验室2025级新生手册 V20250901》。
标注 [假设] 的条目是手册未明确、本项目自行设定的，上线前需实验室确认。

【规则版本化】
RULE_VERSION 会写入每条考评记录。手册每年更新（如 V20260901），
届时把新规则做成新的常量集合、递增版本号，历史考评仍能追溯到
"当时是按哪版规则算的"。切勿直接改旧常量。
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

# ============================================================ 版本
RULE_VERSION = "V20250901"
RULE_SOURCE = "《实验室2025级新生手册 V20250901》"

# ============================================================ 时间常量
# [手册] 日常管理须知 第一章 第一条：考勤 8:30—21:00
CHECK_IN_DEADLINE = time(8, 30)
CHECK_OUT_DEADLINE = time(21, 0)

# [假设] 手册只说“严重迟到”，未给阈值；这里取晚于 9:30 视为严重迟到
SEVERE_LATE_AFTER = time(9, 30)

WEEKDAY_CN = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

# ============================================================ 考勤扣分表
# [手册] 第一章 第八条
DEDUCT = {
    "absent": 10,          # 缺勤
    "absent_late": 5,      # 旷工迟到
    "missing_card": 5,     # 缺卡
    "severe_late": 4,      # 严重迟到、早退
    "late": 2,             # 迟到
    "leave_personal": 2,   # 事假 2 分/半天
    "leave_sick": 1,       # 病假 1 分/半天
    "seminar_absent": 5,   # Seminar/例会缺勤
    "seminar_leave": 2,    # Seminar/例会请假
}

# 状态中文名
STATUS_CN = {
    "present": "正常",
    "late": "迟到",
    "severe_late": "严重迟到",
    "early": "早退",
    "missing_card": "缺卡",
    "absent": "缺勤",
    "leave_personal": "事假",
    "leave_sick": "病假",
    "weekend": "不考勤",
    "exempt": "免考勤",
    "seminar_absent": "Seminar 缺勤",
    "seminar_leave": "Seminar 请假",
}

# ============================================================ 任务分强制分布
# [手册] 津贴规定 一、4、1）：优秀 10%、良好 20%、中等 30%、合格 40%
# 每项为 (名称, 区间下限, 区间上限, 比例)
BANDS = [
    ("优秀", 90, 100, 0.10),
    ("良好", 80, 89, 0.20),
    ("中等", 70, 79, 0.30),
    ("合格", 60, 69, 0.40),
]

# ============================================================ 津贴
# [手册] 津贴规定 一、1：博士 1000；硕士 I 类助研 200；硕士 II 类助研 500
BASE_ALLOWANCE = {
    "phd": 1000.0,
    "master_I": 200.0,
    "master_II": 500.0,
}

# [手册] 津贴规定 一、2：等级与发放比例
PAYOUT_RULES = [
    # (等级, S 下限, S 上限, 发放比例)
    ("A", 96, 999, 1.50),
    ("A", 90, 95.999, 1.40),
    ("A", 86, 89.999, 1.20),
    ("A", 80, 85.999, 1.10),
    ("B", 76, 79.999, 1.00),
    ("B", 70, 75.999, 0.90),
    ("C", 66, 69.999, 0.80),
    ("C", 60, 65.999, 0.70),
    ("D", 50, 59.999, 0.60),
    ("D", -999, 49.999, 0.00),
]


# ============================================================ 时间工具
def week_key(d: date | None = None) -> str:
    """ISO 周，跨年安全：2027-01-01 属于 2026-W53。"""
    d = d or date.today()
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


def month_key(d: date | None = None) -> str:
    d = d or date.today()
    return f"{d.year}-{d.month:02d}"


def week_monday(d: date | None = None) -> date:
    d = d or date.today()
    return d - timedelta(days=d.weekday())


def parse_month(mk: str) -> tuple[int, int]:
    y, m = mk.split("-")
    return int(y), int(m)


def month_days(mk: str) -> list[date]:
    y, m = parse_month(mk)
    first = date(y, m, 1)
    nxt = date(y + 1, 1, 1) if m == 12 else date(y, m + 1, 1)
    return [first + timedelta(days=i) for i in range((nxt - first).days)]


def is_weekend(d: date) -> bool:
    """[手册] 第一章 第三条：周六周日不考勤。"""
    return d.weekday() >= 5


def workdays_between(start: date, end: date) -> int:
    """start 之后到 end（含）之间的工作日数，用于补卡时效判断。"""
    if end <= start:
        return 0
    n = 0
    d = start + timedelta(days=1)
    while d <= end:
        if not is_weekend(d):
            n += 1
        d += timedelta(days=1)
    return n


def hhmm_to_time(s: str | None) -> time | None:
    if not s:
        return None
    try:
        h, m = s.strip().split(":")[:2]
        return time(int(h), int(m))
    except (ValueError, AttributeError):
        return None


# ============================================================ 考勤判定
def judge_attendance(
    check_in: str | None,
    check_out: str | None,
    leave: dict | None = None,
    d: date | None = None,
) -> tuple[str, float, str]:
    """判定某一天的考勤状态。

    参数
    ----
    check_in / check_out : 'HH:MM' 或 None
    leave : {'kind': 'personal'|'sick', 'half': 'am'|'pm'|'full'} 或 None
    d     : 日期，用于判断周末

    返回 (状态, 扣分, 说明)
    """
    if d is not None and is_weekend(d):
        return "weekend", 0, "周末不考勤"

    # 请假优先于打卡判定（请假当天不需要打卡）
    if leave:
        kind = leave.get("kind")
        half = leave.get("half", "full")
        halves = 2 if half == "full" else 1
        if kind == "sick":
            return "leave_sick", DEDUCT["leave_sick"] * halves, f"病假 {halves} 个半天"
        return (
            "leave_personal",
            DEDUCT["leave_personal"] * halves,
            f"事假 {halves} 个半天",
        )

    t_in = hhmm_to_time(check_in)
    t_out = hhmm_to_time(check_out)

    # 一次都没打 -> 缺勤
    if t_in is None and t_out is None:
        return "absent", DEDUCT["absent"], "未打卡且无请假记录"

    # 只打了一次 -> 缺卡
    if t_in is None or t_out is None:
        return "missing_card", DEDUCT["missing_card"], "早晚只打了一次卡"

    # 早退优先于迟到判定（都是问题，取较重的）
    if t_out < CHECK_OUT_DEADLINE and t_in > CHECK_IN_DEADLINE:
        # 两头都有问题，按严重迟到计（手册未给组合规则，[假设]取重）
        return "severe_late", DEDUCT["severe_late"], "迟到且早退"

    if t_out < CHECK_OUT_DEADLINE:
        return "early", DEDUCT["severe_late"], "早退"

    if t_in > SEVERE_LATE_AFTER:
        return "severe_late", DEDUCT["severe_late"], "严重迟到"

    if t_in > CHECK_IN_DEADLINE:
        return "late", DEDUCT["late"], "迟到"

    return "present", 0, "正常"


def attendance_month(daily: list[dict]) -> dict:
    """汇总一个月考勤。

    daily: [{'date': date, 'status': str, 'deduction': float, 'note': str}, ...]

    返回 {'score', 'total_deduction', 'breakdown': {status: {'count', 'points'}}, 'days'}
    """
    total = 0.0
    breakdown: dict[str, dict] = {}
    for row in daily:
        st = row["status"]
        pts = row.get("deduction", 0) or 0
        total += pts
        if st in ("present", "weekend", "exempt"):
            continue
        b = breakdown.setdefault(st, {"count": 0, "points": 0.0})
        b["count"] += 1
        b["points"] += pts

    return {
        "score": max(0.0, 100.0 - total),
        "total_deduction": total,
        "breakdown": breakdown,
        "days": daily,
    }


# ============================================================ 强制分布
def allocate_counts(total: int, bands=BANDS) -> list[int]:
    """把 total 个名额按比例分配，用最大余数法保证总数精确。

    例：total=3 → [0, 1, 1, 1]；total=10 → [1, 2, 3, 4]
    """
    if total <= 0:
        return [0] * len(bands)

    raw = [b[3] * total for b in bands]
    base = [int(x) for x in raw]
    remainder = total - sum(base)

    # 余数大的优先拿到名额
    order = sorted(range(len(raw)), key=lambda i: raw[i] - base[i], reverse=True)
    for i in range(remainder):
        base[order[i]] += 1
    return base


def forced_distribution(raw_scores: list[float], bands=BANDS) -> list[dict]:
    """按强制分布给每个人分配学术任务分。

    raw_scores 按任意顺序传入，内部按分数降序排名。
    返回与输入同序的 [{'rank','bucket','score'}]

    手册要求 10/20/30/40 的硬性比例，因此这里给的是“位次分”而非绝对分。
    """
    n = len(raw_scores)
    if n == 0:
        return []

    # 降序排名（分数相同按原顺序稳定）
    order = sorted(range(n), key=lambda i: (-raw_scores[i], i))
    counts = allocate_counts(n, bands)

    result: list[dict] = [None] * n  # type: ignore[list-item]
    pos = 0
    for (name, lo, hi, _ratio), k in zip(bands, counts):
        for j in range(k):
            idx = order[pos + j]
            if k == 1:
                score = float(hi)          # 独占一档给该档上限
            else:
                span = hi - lo
                score = round(hi - span * j / (k - 1), 1)
            result[idx] = {
                "rank": pos + j + 1,
                "bucket": name,
                "score": score,
            }
        pos += k
    return result


# ============================================================ 总分与发放
def compute_s(attendance_score: float, task_score: float, enable_score: float) -> float:
    """[手册] 津贴规定 一、2：S = 考勤分*40% + 任务分*60% + 赋能分*30%"""
    return round(attendance_score * 0.4 + task_score * 0.6 + enable_score * 0.3, 2)


def grade_and_payout(S: float, attendance_score: float) -> tuple[str, float, str]:
    """返回 (等级, 发放比例, 说明)。

    [手册] D 档特例：考勤分低于 50 或总分低于 50 -> 0%
    """
    if attendance_score < 50:
        return "D", 0.0, "考勤分低于 50，本月津贴不予发放"
    for grade, lo, hi, ratio in PAYOUT_RULES:
        if lo <= S <= hi:
            return grade, ratio, ""
    return "D", 0.0, "分数异常，按不合格处理"


def base_allowance(degree: str, assist_type: str | None) -> float:
    """[手册] 博士 1000；硕士 I 类 200；II 类 500。"""
    if degree == "phd":
        return BASE_ALLOWANCE["phd"]
    if assist_type == "I":
        return BASE_ALLOWANCE["master_I"]
    if assist_type == "II":
        return BASE_ALLOWANCE["master_II"]
    return 0.0


def final_amount(base: float, ratio: float) -> float:
    return round(base * ratio, 2)


# ============================================================ 周报
MIN_REPORT_CHARS = 200  # [手册] 第二章 第二条：工作简述应不少于 200 字
REPORT_DAYS = WEEKDAY_CN[:5]  # 周一到周五，[手册] 第三章 第一条：一周 5 天


def count_chars(text: str | None) -> int:
    """统计有效字数：去掉所有空白字符后的长度。"""
    if not text:
        return 0
    return len("".join(text.split()))


def check_report(
    daily: dict[str, str], summary: str, next_plan: str
) -> tuple[bool, list[str]]:
    """校验周报是否达标。返回 (是否通过, 问题列表)。

    daily 为 {'周一': '上午…下午…晚上…', ...}，按天结构化填写。
    [手册] 第二章第二条要求细化到每个时段，因此这里逐天校验，
    比在自由文本里找"周一/周二"可靠得多。
    """
    problems: list[str] = []

    daily = daily or {}
    empty_days = [d for d in REPORT_DAYS if not (daily.get(d) or "").strip()]
    if empty_days:
        problems.append("以下日期未填写：" + "、".join(empty_days))

    total = sum(count_chars(v) for v in daily.values())
    total += count_chars(summary) + count_chars(next_plan)
    if total < MIN_REPORT_CHARS:
        problems.append(f"工作简述共 {total} 字，不足 {MIN_REPORT_CHARS} 字")

    if not (summary or "").strip():
        problems.append("缺少本周总结")
    if not (next_plan or "").strip():
        problems.append("缺少下周计划")

    return (len(problems) == 0, problems)


def report_word_count(daily: dict[str, str], summary: str, next_plan: str) -> int:
    total = sum(count_chars(v) for v in (daily or {}).values())
    return total + count_chars(summary) + count_chars(next_plan)


# ============================================================ 补卡
# [手册] 第一章 第六条：3 个工作日内，每月不超过 3 次
MAKEUP_LIMIT = 3
MAKEUP_WORKDAYS = 3


def check_makeup(used: int, target: date, today: date | None = None) -> tuple[bool, str]:
    today = today or date.today()
    if used >= MAKEUP_LIMIT:
        return False, f"本月补卡已用 {used} 次，达到上限 {MAKEUP_LIMIT} 次"
    if target >= today:
        return False, "只能为过去的日期补卡"
    gap = workdays_between(target, today)
    if gap > MAKEUP_WORKDAYS:
        return False, f"距该日已过 {gap} 个工作日，超过 {MAKEUP_WORKDAYS} 个工作日上限"
    return True, ""
