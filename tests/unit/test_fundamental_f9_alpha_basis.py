"""F9 选股回测验证：alpha 必须**同基对比**（P1「用历史验证理论」的核心）。

需求 §3.3 F9：批量历史时点选股，「验证长赢理论是否跑赢指数」。
因此 alpha（选股均值 − 指数均值）是唯一的验收数字，它的口径必须对。

实测（V731 审计）发现旧实现**不同基相减**：
  - ``overall`` 用**所有期**的个股收益平均；
  - ``index_stats`` 只用**有指数数据的那些期**平均。
当某期指数取不到时（``index_performance`` 异常返回 ``{}``，如断网/接口失败，
见 pipeline.py:346），该期个股收益仍计入分子、指数却不计入基准 ⇒ alpha
被系统性扭曲。

实测构造：3 期，个股每期 +5%，指数分别为 +10% / 缺失 / +10%。
  - 旧实现：alpha = 5 − 10 = −5（个股基 3 期 vs 指数基 2 期，**不同基**）
  - 正确：只在 2 个「双方都有值」的期上对比 ⇒ alpha = 5 − 10 = −5，
    但**口径明确为 n_periods=2**，且不会混入无基准的期。

另一个已验证无误的口径（对照组，防止修坏）：
  多期个股均值**按股票加权**而非按期数简单平均。实测 10 只 +100% 与
  2 只 −50% ⇒ 75.0（正确），而非 25.0（期数平均的错误值）。
"""

from __future__ import annotations

from easy_tdx.fundamental.pipeline import _summarize_periods


def _period(stock_ret, index_ret, n: int = 1):
    return {
        "results": [
            {"category": "tree", "performance": {"ret_20d": stock_ret}} for _ in range(n)
        ],
        "index": {"ret_20d": index_ret},
    }


class TestOverallWeighting:
    """对照组：多期个股均值按股票加权（这条旧实现就是对的，别修坏）。"""

    def test_weighted_by_stock_not_by_period(self) -> None:
        periods = [_period(100.0, 0.0, n=10), _period(-50.0, 0.0, n=2)]
        avg = _summarize_periods(periods, (20,))["overall"]["ret_20d"]["avg"]
        assert avg == 75.0, f"应按股票加权得 75.0，实得 {avg}（25.0 说明用了期数平均）"


class TestAlphaSameBasis:
    """alpha 只在「个股与指数都有值」的期上计算。"""

    def test_missing_index_period_is_excluded(self) -> None:
        """指数缺失的那一期，不得只把个股算进 alpha。"""
        periods = [
            _period(5.0, 10.0),
            _period(5.0, None),  # 指数缺失
            _period(5.0, 10.0),
        ]
        s = _summarize_periods(periods, (20,))
        b = s["beats_index"]["ret_20d"]
        # 同基：只有 2 期参与（两期指数都有值）
        assert b["n_periods"] == 2, f"应只有 2 期参与 alpha，实得 {b['n_periods']}"
        assert b["alpha"] == -5.0, f"alpha 应为 -5.0，实得 {b['alpha']}"

    def test_no_valid_period_gives_none(self) -> None:
        """所有期都没有指数基准时，alpha 应为 None（不能拿个股均值冒充）。"""
        periods = [_period(5.0, None), _period(5.0, None)]
        b = _summarize_periods(periods, (20,))["beats_index"]["ret_20d"]
        assert b["alpha"] is None, "无基准时不应给出 alpha"
        assert b["beats"] is False

    def test_all_periods_valid(self) -> None:
        """全部期都有数据时，alpha 应基于全部期。"""
        periods = [_period(5.0, 1.0), _period(5.0, 1.0)]
        b = _summarize_periods(periods, (20,))["beats_index"]["ret_20d"]
        assert b["n_periods"] == 2
        assert b["alpha"] == 4.0
        assert b["beats"] is True

    def test_period_without_stock_returns_excluded(self) -> None:
        """个股无收益的期（如无行情）也不参与，避免拉低均值。"""
        periods = [_period(5.0, 1.0), _period(None, 1.0)]
        b = _summarize_periods(periods, (20,))["beats_index"]["ret_20d"]
        assert b["n_periods"] == 1, "个股无收益的那期应被排除"
        assert b["alpha"] == 4.0
