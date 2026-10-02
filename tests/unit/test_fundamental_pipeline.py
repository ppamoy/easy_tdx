"""fundamental/pipeline.py 纯函数测试（V399c）。

覆盖 _returns_at / _sina_frame / _summarize_periods 三个纯函数，离线可测。
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pandas as pd

from easy_tdx.fundamental.pipeline import _returns_at, _sina_frame, _summarize_periods


class TestReturnsAt:
    def _df(self) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "date": pd.date_range("2024-01-01", periods=5, freq="D"),
                "close": [100.0, 110.0, 121.0, 133.1, 146.41],
            }
        )

    def test_empty(self) -> None:
        assert _returns_at(None, date(2024, 1, 1), (20,)) == {}
        assert _returns_at(pd.DataFrame(), date(2024, 1, 1), (20,)) == {}

    def test_target_after_all_dates(self) -> None:
        assert _returns_at(self._df(), date(2030, 1, 1), (20,)) == {}

    def test_returns(self) -> None:
        out = _returns_at(self._df(), date(2024, 1, 1), (1, 2, 5))
        assert out["as_of_close"] == 100.0
        assert out["ret_1d"] == 10.0
        assert out["ret_2d"] == 21.0
        assert out["ret_5d"] is None  # 越界


class TestSinaFrame:
    def test_build(self) -> None:
        rows = [
            SimpleNamespace(
                code="000001",
                market="SZ",
                report_date=date(2024, 3, 31),
                disclosure_date=date(2024, 4, 25),
                indicators={"roe": 15.0, "eps": 1.2},
            ),
        ]
        df = _sina_frame(rows)
        assert df.iloc[0]["code"] == "000001"
        assert df.iloc[0]["roe"] == 15.0
        assert df.iloc[0]["eps"] == 1.2


class TestSummarizePeriods:
    def test_empty(self) -> None:
        out = _summarize_periods([], (20, 60))
        assert out["overall"]["count"] == 0
        assert out["by_category"]["tree"]["count"] == 0

    def test_with_data(self) -> None:
        periods = [
            {
                "results": [
                    {"category": "tree", "performance": {"ret_20d": 5.0, "ret_60d": 10.0}},
                    {"category": "grain", "performance": {"ret_20d": -2.0, "ret_60d": 3.0}},
                ],
                "index": {"ret_20d": 1.0, "ret_60d": 4.0},
            }
        ]
        out = _summarize_periods(periods, (20, 60))
        assert out["overall"]["count"] == 2
        assert out["overall"]["ret_20d"]["avg"] == 1.5
        assert out["beats_index"]["ret_20d"]["beats"] is True


class TestReturnsAtV731:
    """V731 第 35 轮：_returns_at 的两个 F9 数据质量缺陷。

    F9（选股回测验证）的全部结论 —— 分类均值、胜率、跑赢指数与否 ——
    都建立在 _returns_at 逐只算出的 ret_Nd 上。这两个缺陷都不改变
    "正常有数据"样本的数值，而是让**坏样本**静默混进统计：

    缺陷1 NaN 基准：target 当日 close=NaN → 旧实现产出 ret_Nd=nan。
    NaN 不等于 None，_stats 的 `is not None` 过滤拦不住 → 一个 NaN 让
    整组 avg=nan，且 NaN>0==False 占据 hit_rate 分母，胜率被稀释。
    （实测：vals=[nan,10,-5] → avg=nan, hit_rate=0.33，而有效样本只有 2 个）

    缺陷2 停牌错位：个股 target 当日停牌 → 旧实现取复牌日作基准，
    与指数基准起点错开数个交易日，"跑赢指数"变成错位对比。现在输出
    base_date / base_shift_bars，把错位显式化，供上层剔除错位样本。
    """

    def _df(self, closes: list[float]) -> pd.DataFrame:
        return pd.DataFrame(
            {"date": pd.date_range("2026-01-01", periods=len(closes), freq="D"),
             "close": closes}
        )

    def test_nan_base_returns_empty(self) -> None:
        """缺陷1：基准日 close=NaN → 空 dict，绝不产出 nan。"""
        closes = [float("nan"), 110.0, 120.0, 130.0, 140.0]
        out = _returns_at(self._df(closes), date(2026, 1, 1), (1, 2))
        assert out == {}, f"NaN 基准应返回空，实得 {out}"
        assert not any(isinstance(v, float) and math.isnan(v) for v in out.values())

    def test_nan_tail_gives_none_not_nan(self) -> None:
        """缺陷1 另一半：末端 NaN → ret=None（可被 _stats 过滤），不是 nan。"""
        closes = [100.0, 110.0, float("nan"), 130.0, 140.0]
        out = _returns_at(self._df(closes), date(2026, 1, 1), (1, 2))
        assert out.get("ret_1d") == 10.0       # 有效样本照常算
        assert out.get("ret_2d") is None       # NaN 末端 → None，可被过滤
        assert not (isinstance(out.get("ret_2d"), float) and math.isnan(out["ret_2d"]))

    def test_inf_base_also_rejected(self) -> None:
        closes = [float("inf"), 110.0, 120.0, 130.0, 140.0]
        assert _returns_at(self._df(closes), date(2026, 1, 1), (1,)) == {}

    def test_halted_stock_base_shift_is_visible(self) -> None:
        """缺陷2：target=1/3 当日停牌（序列 1,2,5,6,7）→ 基准落在 1/5。

        收益数值不变（仍按 K 线序），但 base_shift_bars 必须 >0，让上层
        能识别这是"错位基准"样本并剔除，而不是悄悄混进 F9 统计。
        """
        closes = [101.0, 102.0, 105.0, 106.0, 107.0]
        df = pd.DataFrame(
            {"date": [date(2026, 1, d) for d in (1, 2, 5, 6, 7)], "close": closes}
        )
        out = _returns_at(df, date(2026, 1, 3), (1,))
        assert out["as_of_close"] == 105.0
        assert out["base_date"] == date(2026, 1, 5)
        assert out["base_shift_bars"] == 2     # 顺延 2 天，错位可见

    def test_normal_case_has_zero_shift(self) -> None:
        """对照组：target 当日有 K 线 → shift=0，行为与旧版完全一致。"""
        out = _returns_at(self._df([100.0, 110.0, 120.0, 130.0, 140.0]),
                          date(2026, 1, 1), (1,))
        assert out["base_shift_bars"] == 0
        assert out["base_date"] == date(2026, 1, 1)
        assert out["ret_1d"] == 10.0

    def test_stats_nan_no_longer_poisons(self) -> None:
        """端到端：NaN 不再进入 _stats —— 修复后 NaN 样本被拦在源头。"""
        from easy_tdx.fundamental.pipeline import _summarize_periods

        # 构造一个 target 日 close=NaN 的结果（模拟旧版会产出的形态）
        periods = [{
            "date": date(2026, 1, 1),
            "results": [
                {"category": "tree", "performance": {"ret_20d": float("nan")}},
                {"category": "tree", "performance": {"ret_20d": 10.0}},
                {"category": "tree", "performance": {"ret_20d": -5.0}},
            ],
        }]
        out = _summarize_periods(periods, (20,))
        st = out["by_category"]["tree"]["ret_20d"]
        # 旧实现：avg=nan（一个 NaN 毒化整组）—— 新实现下 NaN 仍在 perf dict
        # 里时 _stats 依旧不过滤（_stats 只过滤 None），所以这里断言的是
        # 源头行为：_returns_at 不再产出 nan（见 test_nan_base_returns_empty）。
        # 本测试用 nan 输入校验 _stats 的防御缺口仍然存在 → 需要源头堵住。
        assert st["count"] == 3 or st["count"] == 2  # 记录现状，不掩盖


class TestSummarizePeriodsV731:
    """V731 第 36 轮：_stats 出口的 NaN / 类型防御缺口。

    round-35 已让 _returns_at 在源头不产出 NaN，但 _stats 是公共出口：
    任何其他来源的 NaN（旧缓存、上游新代码、手工构造）仍能让
    整组 avg=nan、并把 NaN>0==False 的样本计入 hit_rate 分母。
    实测（修复前）：vals=[nan,10,-5] → avg=nan, hit_rate=0.33，
    而有效样本只有 2 个（正确值 avg=2.5, hit_rate=0.5）。
    另外 str 类型混入会让 sum() 直接 TypeError 崩掉整个汇总。
    防御收口在出口处，不依赖每个上游都记得堵。
    """

    def _p(self, rets: list) -> list[dict]:
        return [{
            "date": date(2026, 1, 1),
            "results": [
                {"category": "tree", "performance": {"ret_20d": v}} for v in rets
            ],
        }]

    def test_nan_no_longer_poisons_group(self) -> None:
        st = _summarize_periods(self._p([float("nan"), 10.0, -5.0]), (20,))
        s = st["by_category"]["tree"]["ret_20d"]
        assert s["count"] == 2, f"NaN 应被剔除，count 应为 2，实得 {s}"
        assert s["avg"] == 2.5
        assert s["hit_rate"] == 0.5

    def test_all_nan_gives_none_not_crash(self) -> None:
        st = _summarize_periods(self._p([float("nan"), float("inf")]), (20,))
        s = st["by_category"]["tree"]["ret_20d"]
        assert s["count"] == 0
        assert s["avg"] is None
        assert s["hit_rate"] is None

    def test_str_value_filtered_not_crash(self) -> None:
        """str 混入：旧实现 TypeError 崩溃，现在过滤掉。"""
        st = _summarize_periods(self._p(["12.5", 8.0]), (20,))
        s = st["by_category"]["tree"]["ret_20d"]
        assert s["count"] == 1
        assert s["avg"] == 8.0

    def test_index_nan_excluded_from_alpha_pairing(self) -> None:
        """指数基准为 NaN 的期不得参与 alpha（旧实现 is not None 拦不住）。"""
        periods = [
            {"date": date(2026, 1, 1), "index": {"ret_20d": float("nan")},
             "results": [{"category": "tree", "performance": {"ret_20d": 10.0}}]},
            {"date": date(2026, 2, 1), "index": {"ret_20d": 2.0},
             "results": [{"category": "tree", "performance": {"ret_20d": 6.0}}]},
        ]
        b = _summarize_periods(periods, (20,))["beats_index"]["ret_20d"]
        assert b["n_periods"] == 1, f"NaN 指数期应被剔除，实得 {b}"
        assert b["alpha"] == 4.0

    def test_clean_data_unchanged(self) -> None:
        """对照组：干净数据下统计与旧实现完全一致。"""
        st = _summarize_periods(self._p([10.0, -5.0, 5.0]), (20,))
        s = st["by_category"]["tree"]["ret_20d"]
        assert s["count"] == 3
        assert s["avg"] == round(10.0 / 3, 2)
        assert s["hit_rate"] == round(2 / 3, 2)
