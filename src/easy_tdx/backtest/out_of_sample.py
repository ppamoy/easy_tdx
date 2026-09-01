"""样本外（Out-of-Sample）验证。

目的：让用户通过历史回测回答「模型在没见过的数据上还准不准」。与分段稳健性
（V97，把全区间切成若干段重跑）不同，本模块把区间按时间顺序切为「训练段 + 样本外
持有段」，策略参数固定，只在训练段上"见过"数据，然后跑到从未见过的持有段上验证：

- 训练段（in-sample）绩效/准确度：参数是在这段上调出来的，容易偏乐观。
- 样本外段（out-of-sample）绩效/准确度：模型从未见过这段，是「真刀真枪」的检验。
- 结论：样本外是否仍正收益、命中率是否仍高于随机基准、与训练段的差距。

输出为 JSON 兼容的纯 Python 类型。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from easy_tdx.backtest.engine import BacktestEngine
from easy_tdx.backtest.strategy import Strategy


def compute_out_of_sample(
    df: Any,
    strategy_factory: Callable[[], Strategy],
    train_ratio: float = 0.7,
    cash: float = 1_000_000.0,
    commission: float = 0.0003,
    stamp_tax: float = 0.001,
    slippage: float = 0.0,
    execution: str = "next_open",
) -> dict[str, Any]:
    """把区间按时间切为训练段与样本外持有段，分别回测并对比。

    Args:
        df: 回测用 OHLCV DataFrame
        strategy_factory: 返回全新策略实例的可调用对象（每段独立实例）
        train_ratio: 训练段占比（0~1），其余为样本外持有段
        cash/commission/stamp_tax/slippage/execution: 与主回测一致

    Returns:
        dict：{"train_ratio", "train_bars", "test_bars",
               "train": {绩效/准确度摘要}, "test": {绩效/准确度摘要},
               "degraded": bool, "verdict": str}
        数据不足时返回含 note 的最小报告。
    """
    if df is None or len(df) == 0:
        return {"note": "无数据", "degraded": False, "verdict": "无数据，无法做样本外验证"}

    n = len(df)
    if n < 120:
        return {
            "note": "数据不足 120 根",
            "degraded": False,
            "verdict": "数据不足 120 根，无法可靠切分训练/样本外段",
        }

    train_n = max(int(n * train_ratio), 60)
    train_df = df.iloc[:train_n].reset_index(drop=True)
    test_df = df.iloc[train_n:].reset_index(drop=True)
    if len(test_df) < 30:
        return {
            "note": "样本外段过短",
            "degraded": False,
            "verdict": "样本外段不足 30 根，无法验证",
        }

    def _run_segment(seg_df: Any) -> dict[str, Any]:
        strategy = strategy_factory()
        engine = BacktestEngine(
            strategy=strategy,
            cash=cash,
            commission=commission,
            stamp_tax=stamp_tax,
            slippage=slippage,
            execution=execution,
        )
        result = engine.run(seg_df)
        perf = result.performance
        # 信号准确度（买入 5 根前瞻命中率/随机基准/超额）
        sa = getattr(result, "signal_accuracy", None) or {}
        buy = sa.get("buy") or {}
        horizons = buy.get("horizons") or {}
        h5 = horizons.get("5") or horizons.get("3")
        closes = seg_df["close"].to_numpy(dtype=float)
        buy_hold = float(closes[-1] / closes[0] - 1.0) if len(closes) > 1 and closes[0] else 0.0
        seg: dict[str, Any] = {
            "bars": len(seg_df),
            "total_return": float(perf.get("total_return", 0.0)),
            "win_rate": float(perf.get("win_rate", 0.0)),
            "sharpe": float(perf.get("sharpe", 0.0)),
            "max_drawdown": float(perf.get("max_drawdown", 0.0)),
            "trades": int(perf.get("total_trades", 0)),
            "buy_hold_return": buy_hold,
            "alpha": float(perf.get("total_return", 0.0)) - buy_hold,
            "hit_rate": float(h5["hit_rate"]) if h5 and h5.get("count", 0) > 0 else None,
            "baseline_hit_rate": (
                float(h5["baseline_hit_rate"]) if h5 and h5.get("count", 0) > 0 else None
            ),
            "excess_hit_rate": (
                float(h5["excess_hit_rate"]) if h5 and h5.get("count", 0) > 0 else None
            ),
        }
        return seg

    train = _run_segment(train_df)
    test = _run_segment(test_df)

    # ── 样本外是否退化的判定 ───────────────────────────────────────────────
    degraded = False
    reasons: list[str] = []

    def _per_bar(ret: float, bars: int) -> float:
        """把总收益折算为每根 K 线的复合收益，便于不同长度段公平比较。"""
        if bars <= 0 or ret <= -1:
            return 0.0
        return float((1.0 + ret) ** (1.0 / bars) - 1.0)

    if test["total_return"] <= 0:
        reasons.append("样本外总收益非正")
        degraded = True
    if test["alpha"] <= 0:
        reasons.append("样本外未跑赢买入持有")
        degraded = True
    if test["excess_hit_rate"] is not None and test["excess_hit_rate"] < 0:
        reasons.append("样本外命中率低于随机基准")
        degraded = True
    # 用每根 K 线复合收益对比，避免「样本外段更短所以总收益天然更小」的误判
    train_per_bar = _per_bar(train["total_return"], int(train["bars"]))
    test_per_bar = _per_bar(test["total_return"], int(test["bars"]))
    if train_per_bar > 0 and test_per_bar < train_per_bar * 0.5:
        reasons.append("样本外每根收益较训练段明显衰减")
        degraded = True

    verdict = _build_oos_verdict(train, test, degraded, reasons)
    return {
        "train_ratio": train_ratio,
        "train_bars": train_n,
        "test_bars": n - train_n,
        "train": train,
        "test": test,
        "degraded": degraded,
        "verdict": verdict,
        "note": None,
    }


def _build_oos_verdict(
    train: dict[str, Any],
    test: dict[str, Any],
    degraded: bool,
    reasons: list[str],
) -> str:
    """生成一句人类可读结论。"""
    t_ret = test["total_return"]
    tr_ret = train["total_return"]
    parts = [
        f"训练段收益 {tr_ret:+.2%} → 样本外 {t_ret:+.2%}",
        "样本外跑赢买入持有" if test["alpha"] > 0 else "样本外未跑赢买入持有",
    ]
    if test["excess_hit_rate"] is not None:
        exc = test["excess_hit_rate"]
        parts.append(f"样本外5根命中率 {test['hit_rate']:.0%}（超额 {exc:+.1%}）")
    else:
        parts.append("样本外无足量买入信号，命中率不可考")
    if degraded:
        return "；".join(parts) + "。⚠ 样本外表现衰减，模型可能存在过拟合，历史成绩需谨慎对待。"
    return "；".join(parts) + "。样本外仍保持正收益与优于基准的表现，模型具备泛化能力。"
