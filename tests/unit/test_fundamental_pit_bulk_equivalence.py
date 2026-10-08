"""V732：PIT 双实现**等价性**回归 —— pick_report 与 pick_reports_bulk 必须选同一行。

缺陷（实测复现，见 docs 与本文件用例）
------------------------------------
``pick_reports_bulk``（向量化，全市场扫描 ``scan_market`` 用）的 docstring 声称
「规则与 pick_report **完全一致**」。实测不成立，共 3 处分叉：

1. **未来数据泄漏（P0，违反 PIT 生命线）**：``disclosure_date`` **有值但无法解析**
   （如 ``"junk"`` / NaN / NaT）时 —— ``pick_report`` 保守排除；而 bulk 版做
   ``pd.to_datetime(errors="coerce")`` 把它变成 NaT，于是落进
   「披露日缺失 ⇒ 用 report_date 近似（≤100 天）」分支被**放行**。
   实测：``report_date=2024-03-31, disclosure_date="junk", target=2024-04-15``
   → pick_report=None，bulk 返回该行。

2. **交叉填充导致排序分叉**：bulk 用 ``_pit_dd=dd.fillna(rd), _pit_rd=rd.fillna(dd)``
   让两条按**不同规则**入选的行互相借用对方日期。实测两行
   ``(rd=2024-03-31, dd=缺失)`` 与 ``(rd=2024-01-31, dd=2024-03-01)``，
   target=2024-04-01 → pick_report 选后者(eps=2.0)，bulk 选前者(eps=1.0)。

3. **groupby.first() 逐列跳过 NaN**：选中行某字段为 None 时会被后续行的值顶替，
   与 pick_report「整行原样返回」不同（bulk 曾报 report_date=2024-03-31 而
   pick_report 报 None）。已改用 ``head(1)``。

修复：bulk 改用与 pick_report **同一个** ``_coerce_date`` 归一化、按
``dd_raw is not None`` 判定缺失、去掉交叉填充、稳定排序 + ``head(1)``。

测试策略
--------
- ``TestReproUnparsableDisclosure``：精确复现上述第 1 条。
- ``TestExhaustiveEquivalence``：**穷举** (report_date × disclosure_date) 组合的
  单行帧与**两两组合**的双行帧，断言两实现选同一行 —— 这是 docstring 那条
  「规则完全一致」声明的最强形式，不依赖源码文本。
- ``TestRandomizedEquivalence``：随机多行帧 + 打乱顺序，同上。
- ``TestNoFutureDataGuard``：任何被选中的行都不得有 disclosure_date > target，
  也不得有未来报告期。
"""

from __future__ import annotations

import random
from datetime import date

import pandas as pd
import pytest

from easy_tdx.fundamental.indicators import pick_report, pick_reports_bulk

TARGET = date(2024, 4, 15)

# report_date 取值空间：≤target / 超 100 天 / 缺失 / 未来
RD_SPACE: list[object] = [
    date(2024, 3, 31),   # 报告期 ≤ target 且距今 15 天（近似可用）
    date(2023, 12, 31),  # 报告期 ≤ target 但距今 106 天 > 100 天（近似越界）
    date(2024, 5, 1),    # 报告期 > target（未来报告期）
    None,                # 报告期缺失
]

# disclosure_date 取值空间：≤target / >target / 真缺失 / 有值但无法解析
DD_SPACE: list[object] = [
    date(2024, 4, 1),    # 披露日 ≤ target（可用）
    date(2024, 6, 1),    # 披露日 > target（未来数据，必须排除）
    None,                # 真缺失 ⇒ 允许报告期近似
    "junk",              # 有值但无法解析 ⇒ 保守排除
    pd.NaT,              # 有值（非 None）但无法解析 ⇒ 保守排除
    float("nan"),        # 同上
]


def _frame(rows: list[tuple[object, object, float]], market: str = "SZ") -> pd.DataFrame:
    """rows: (report_date, disclosure_date, tag)；tag 兼作唯一行标识与 eps。"""
    return pd.DataFrame(
        [
            {
                "code": "C1",
                "market": market,
                "report_date": rd,
                "disclosure_date": dd,
                "eps": tag,
            }
            for rd, dd, tag in rows
        ]
    )


def _selected_tag(frame: pd.DataFrame, target: date, market: str = "SZ") -> float | None:
    """返回被选中行的 tag；None = 两实现都未选中。不一致则 pytest.fail。"""
    single = pick_report(frame, "C1", target, market=market)
    bulk = pick_reports_bulk(frame, target)
    n = 0 if bulk.empty else len(bulk)

    a = None if single is None else float(single["eps"])
    if n == 0:
        b = None
    elif n == 1:
        b = float(bulk.iloc[0]["eps"])
    else:
        pytest.fail(f"bulk 应每只股票返回 1 行，实际 {n} 行")

    rows_repr = frame[["report_date", "disclosure_date", "eps"]].to_dict("records")
    assert a == b, (
        f"两实现分叉：pick_report={a} pick_reports_bulk={b} "
        f"target={target} rows={rows_repr}"
    )
    return a


class TestReproUnparsableDisclosure:
    """精确复现：披露日有值但无法解析 ⇒ 两实现都必须排除（不得退回报告期近似）。"""

    def test_junk_disclosure_excluded_by_both(self) -> None:
        """任务书给的原始复现：('Y','sz',2024-03-31,'junk',1.0)。"""
        df = pd.DataFrame(
            [
                {
                    "code": "Y",
                    "market": "sz",
                    "report_date": date(2024, 3, 31),
                    "disclosure_date": "junk",
                    "eps": 1.0,
                }
            ]
        )
        target = date(2024, 4, 15)
        assert pick_report(df, "Y", target) is None, "pick_report 应保守排除该行"
        out = pick_reports_bulk(df, target)
        assert len(out) == 0, (
            f"pick_reports_bulk 泄漏：返回了 {len(out)} 行 "
            f"(eps={out['eps'].tolist() if not out.empty else []})——"
            "无法解析的披露日被当成「缺失」并退回报告期近似，等于放行未知披露状态"
        )

    @pytest.mark.parametrize("bad", ["junk", pd.NaT, float("nan"), "", "not-a-date"])
    def test_unparsable_disclosure_never_admitted(self, bad: object) -> None:
        """扩展：各种「有值但无法解析」的披露日都不得放行。"""
        for rd in (date(2024, 3, 31), date(2024, 4, 14)):
            assert _selected_tag(_frame([(rd, bad, 1.0)]), TARGET) is None, (
                f"披露日 {bad!r} 报告期 {rd} 不应被选中"
            )

    def test_truly_missing_disclosure_still_approximated(self) -> None:
        """对照组：真 None 才算缺失，仍允许报告期近似（不能矫枉过正）。"""
        assert _selected_tag(_frame([(date(2024, 3, 31), None, 7.0)]), TARGET) == 7.0
        # 报告期距今 > 100 天 ⇒ 近似越界，排除
        assert _selected_tag(_frame([(date(2023, 12, 31), None, 8.0)]), TARGET) is None


class TestCrossFillDivergence:
    """复现第 2 条：交叉填充让两实现选到不同的行。"""

    def test_mixed_admission_rules_pick_same_row(self) -> None:
        rows = [
            (date(2024, 3, 31), None, 1.0),           # 走「报告期近似」入选
            (date(2024, 1, 31), date(2024, 3, 1), 2.0),  # 走「披露日已知」入选
        ]
        assert _selected_tag(_frame(rows), date(2024, 4, 1)) == 2.0

    def test_two_approximated_rows_pick_latest_period(self) -> None:
        rows = [
            (date(2024, 2, 29), None, 1.0),
            (date(2024, 3, 31), None, 2.0),
        ]
        assert _selected_tag(_frame(rows), TARGET) == 2.0

    def test_selected_row_fields_not_backfilled(self) -> None:
        """选中行 report_date 缺失时，不得被同组后续行的值顶替（groupby.first 坑）。"""
        rows = [
            (None, date(2024, 4, 10), 1.0),            # 会被选中
            (date(2024, 3, 31), date(2024, 4, 1), 2.0),
        ]
        f = _frame(rows)
        single = pick_report(f, "C1", TARGET)
        bulk = pick_reports_bulk(f, TARGET)
        assert single is not None and not bulk.empty
        assert single["report_date"] is None
        assert bulk.iloc[0]["report_date"] is None, (
            f"bulk 把 report_date 回填成了 {bulk.iloc[0]['report_date']!r}（逐股是 None）"
        )


class TestExhaustiveEquivalence:
    """穷举等价性 —— 直接编码 docstring 的「规则完全一致」声明。"""

    @pytest.mark.parametrize("rd", RD_SPACE)
    @pytest.mark.parametrize("dd", DD_SPACE)
    def test_single_row_all_combinations(self, rd: object, dd: object) -> None:
        _selected_tag(_frame([(rd, dd, 1.0)]), TARGET)

    def test_all_ordered_pairs(self) -> None:
        """两两组合（含重复组合）→ 覆盖排序键与入选规则的交互。"""
        combos = [(rd, dd) for rd in RD_SPACE for dd in DD_SPACE]
        for i, (rd_a, dd_a) in enumerate(combos):
            for rd_b, dd_b in combos:
                _selected_tag(
                    _frame([(rd_a, dd_a, 1.0), (rd_b, dd_b, 2.0)]),
                    TARGET,
                )

    def test_all_triples(self) -> None:
        combos = [(rd, dd) for rd in RD_SPACE for dd in DD_SPACE]
        rng = random.Random(20240415)
        # 24^3 = 13824 太多，取有代表性的 400 组三元组（含大量重复组合）
        for _ in range(400):
            rows = [
                (rd, dd, float(i + 1))
                for i, (rd, dd) in enumerate(rng.sample(combos, 3))
            ]
            _selected_tag(_frame(rows), TARGET)


class TestRandomizedEquivalence:
    """随机帧 + 打乱顺序：两实现必须始终一致且顺序无关。"""

    @pytest.mark.parametrize("seed", range(30))
    def test_random_frame_equivalence(self, seed: int) -> None:
        rng = random.Random(seed)
        n = rng.randint(1, 6)
        rows = [
            (rng.choice(RD_SPACE), rng.choice(DD_SPACE), float(i + 1)) for i in range(n)
        ]
        got = _selected_tag(_frame(rows), TARGET)

        # 顺序无关性：打乱后两实现仍一致、且选中的 tag 不变
        for s in range(3):
            shuffled = list(rows)
            random.Random(seed * 10 + s).shuffle(shuffled)
            assert _selected_tag(_frame(shuffled), TARGET) == got, f"seed={seed} 顺序影响结果"

    def test_multi_code_multi_market(self) -> None:
        """多股票/多市场：bulk 按 (code, market) 分组，逐股版按 code+market 过滤。"""
        rng = random.Random(7)
        recs = []
        for code, market in (("A", "SZ"), ("A", "SH"), ("B", "SZ"), ("C", "SH")):
            for i in range(3):
                recs.append(
                    {
                        "code": code,
                        "market": market,
                        "report_date": rng.choice(RD_SPACE),
                        "disclosure_date": rng.choice(DD_SPACE),
                        "eps": float(len(recs) + 1),
                    }
                )
        f = pd.DataFrame(recs)
        bulk = pick_reports_bulk(f, TARGET)
        got = {(r["code"], r["market"]): float(r["eps"]) for _, r in bulk.iterrows()}
        for (code, market), tag in got.items():
            single = pick_report(f, code, TARGET, market=market)
            assert single is not None, f"{code}/{market}: 逐股无、批量有 {tag}"
            assert float(single["eps"]) == tag, f"{code}/{market} 分叉: {single['eps']} vs {tag}"
        # 反向：逐股有结果而批量没有 ⇒ 也是分叉
        for code, market in (("A", "SZ"), ("A", "SH"), ("B", "SZ"), ("C", "SH")):
            single = pick_report(f, code, TARGET, market=market)
            if single is not None:
                assert (code, market) in got, f"{code}/{market}: 批量缺失"


class TestNoFutureDataGuard:
    """守卫：被选中的行绝不能来自未来。"""

    def _check_no_future(self, frame: pd.DataFrame, target: date) -> None:
        bulk = pick_reports_bulk(frame, target)
        ts = pd.Timestamp(target)
        for _, r in bulk.iterrows():
            dd = r.get("disclosure_date")
            d = pd.to_datetime(dd, errors="coerce")
            rd = pd.to_datetime(r.get("report_date"), errors="coerce")
            if pd.notna(d):
                assert d <= ts, f"泄漏：披露日 {d.date()} > 时点 {target}"
                # 自洽数据下（报告期 ≤ 披露日）报告期不可能在未来
                if pd.notna(rd) and rd <= d:
                    assert rd <= ts, f"泄漏：报告期 {rd.date()} > 时点 {target}"
            else:
                # 走报告期近似分支：必须 ≤ target 且相差 ≤100 天
                assert pd.notna(rd), "披露日与报告期都缺失却仍被选中"
                assert rd <= ts, f"泄漏：近似分支报告期 {rd.date()} > 时点 {target}"
                assert (ts - rd) <= pd.Timedelta(days=100), "近似分支超出 100 天"

    def test_future_disclosures_never_selected(self) -> None:
        rows = [
            (date(2024, 3, 31), date(2024, 4, 1), 1.0),   # 合法
            (date(2024, 6, 30), date(2024, 8, 26), 2.0),  # 未来披露 + 未来报告期
            (date(2025, 12, 31), date(2026, 4, 29), 3.0),  # 远超 target
            (date(2024, 3, 31), "junk", 4.0),             # 不可解析
        ]
        f = _frame(rows)
        self._check_no_future(f, TARGET)
        assert _selected_tag(f, TARGET) == 1.0

    def test_guard_on_random_frames(self) -> None:
        rng = random.Random(99)
        for _ in range(50):
            rows = [
                (rng.choice(RD_SPACE), rng.choice(DD_SPACE), float(i + 1))
                for i in range(rng.randint(1, 5))
            ]
            self._check_no_future(_frame(rows), TARGET)
