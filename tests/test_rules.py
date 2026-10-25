# -*- coding: utf-8 -*-
"""规则引擎测试 —— 与 v1 相同的断言，验证搬迁后行为未变。"""

from datetime import date

from app import rules as R


class TestAttendanceJudge:
    def test_normal(self):
        d = date(2026, 10, 21)  # 周三
        assert R.judge_attendance("08:20", "21:10", None, d)[0] == "present"

    def test_on_time_boundary(self):
        d = date(2026, 10, 21)
        assert R.judge_attendance("08:30", "21:00", None, d)[0] == "present"

    def test_late(self):
        d = date(2026, 10, 21)
        assert R.judge_attendance("08:31", "21:00", None, d)[0] == "late"

    def test_severe_late(self):
        d = date(2026, 10, 21)
        assert R.judge_attendance("09:40", "21:00", None, d)[0] == "severe_late"

    def test_early_leave(self):
        d = date(2026, 10, 21)
        assert R.judge_attendance("08:20", "20:00", None, d)[0] == "early"

    def test_missing_card(self):
        d = date(2026, 10, 21)
        assert R.judge_attendance("08:20", None, None, d)[0] == "missing_card"

    def test_absent(self):
        d = date(2026, 10, 21)
        assert R.judge_attendance(None, None, None, d)[0] == "absent"

    def test_weekend(self):
        assert R.judge_attendance(None, None, None, date(2026, 10, 24))[0] == "weekend"

    def test_leave(self):
        d = date(2026, 10, 21)
        assert R.judge_attendance(None, None, {"kind": "sick", "half": "full"}, d)[1] == 2
        assert R.judge_attendance(None, None, {"kind": "personal", "half": "am"}, d)[1] == 2


class TestDeductions:
    def test_all_values(self):
        assert R.DEDUCT["absent"] == 10
        assert R.DEDUCT["missing_card"] == 5
        assert R.DEDUCT["severe_late"] == 4
        assert R.DEDUCT["late"] == 2
        assert R.DEDUCT["leave_personal"] == 2
        assert R.DEDUCT["leave_sick"] == 1
        assert R.DEDUCT["seminar_absent"] == 5


class TestAllocation:
    def test_ten_people(self):
        assert R.allocate_counts(10) == [1, 2, 3, 4]

    def test_conservation(self):
        for n in range(1, 101):
            assert sum(R.allocate_counts(n)) == n, f"n={n}"

    def test_forced_distribution_buckets(self):
        scores = [95, 88, 76, 65, 92, 81, 70, 62, 90, 85]
        res = R.forced_distribution(scores)
        buckets = [r["bucket"] for r in res]
        assert buckets.count("优秀") == 1
        assert buckets.count("良好") == 2
        assert buckets.count("中等") == 3
        assert buckets.count("合格") == 4

    def test_single_person(self):
        r = R.forced_distribution([50.0])
        assert r[0]["bucket"] == "合格"
        assert r[0]["score"] == 69.0

    def test_empty(self):
        assert R.forced_distribution([]) == []


class TestFormula:
    def test_s_value(self):
        assert R.compute_s(92, 85, 40) == 99.8

    def test_grades(self):
        assert R.grade_and_payout(99.8, 90)[:2] == ("A", 1.50)
        assert R.grade_and_payout(95.9, 90)[:2] == ("A", 1.40)
        assert R.grade_and_payout(86, 90)[:2] == ("A", 1.20)
        assert R.grade_and_payout(80, 90)[:2] == ("A", 1.10)
        assert R.grade_and_payout(79.9, 90)[:2] == ("B", 1.00)
        assert R.grade_and_payout(70, 90)[:2] == ("B", 0.90)
        assert R.grade_and_payout(60, 90)[:2] == ("C", 0.70)
        assert R.grade_and_payout(59.9, 90)[:2] == ("D", 0.60)

    def test_attendance_below_50_zero(self):
        assert R.grade_and_payout(85, 49)[:2] == ("D", 0.00)

    def test_base_allowance(self):
        assert R.base_allowance("phd", None) == 1000.0
        assert R.base_allowance("master", "I") == 200.0
        assert R.base_allowance("master", "II") == 500.0


class TestReport:
    def test_valid(self):
        daily = {d: "上午精读论文两节并整理公式推导，下午跑对比实验记录显存占用，晚上复盘数据并写当日小结。"
                 for d in R.REPORT_DAYS}
        ok, probs = R.check_report(daily, "本周完成 baseline 复现第一阶段，跑通两组对比实验。",
                                   "下周完成剩余消融实验并整理成表。")
        assert ok, probs

    def test_missing_days(self):
        ok, probs = R.check_report({"周一": "读论文"}, "总结", "计划")
        assert not ok
        assert any("未填写" in p for p in probs)

    def test_too_short(self):
        daily = {d: "读论文" for d in R.REPORT_DAYS}
        ok, probs = R.check_report(daily, "完成", "继续")
        assert not ok
        assert any("不足" in p for p in probs)


class TestMakeup:
    def test_within_three_workdays(self):
        today = date(2026, 10, 23)
        assert R.check_makeup(0, date(2026, 10, 22), today)[0]
        assert R.check_makeup(0, date(2026, 10, 21), today)[0]

    def test_beyond(self):
        today = date(2026, 10, 23)
        assert not R.check_makeup(0, date(2026, 10, 19), today)[0]

    def test_limit(self):
        today = date(2026, 10, 23)
        assert not R.check_makeup(3, date(2026, 10, 22), today)[0]

    def test_today_not_allowed(self):
        today = date(2026, 10, 23)
        assert not R.check_makeup(0, today, today)[0]


class TestTimeUtils:
    def test_week_key_cross_year(self):
        assert R.week_key(date(2027, 1, 1)) == "2026-W53"
        assert R.week_key(date(2026, 1, 1)) == "2026-W01"
        assert R.week_key(date(2026, 10, 24)) == "2026-W43"

    def test_month_days(self):
        assert len(R.month_days("2026-02")) == 28
        assert len(R.month_days("2028-02")) == 29
        assert len(R.month_days("2026-12")) == 31


class TestRuleVersion:
    def test_version_declared(self):
        assert R.RULE_VERSION == "V20250901"
        assert "2025" in R.RULE_SOURCE
