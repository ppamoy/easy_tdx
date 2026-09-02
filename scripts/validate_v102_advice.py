#!/usr/bin/env python3
"""V102 决策支持建议实证：把模型给出的入场/止损/止盈建议放到历史 K 线上回放。

运行方式：
    cd /home/skp/workspace/easy_tdx
    source .venv/bin/activate
    python scripts/validate_v102_advice.py

说明：
- 在合成行情上生成多笔 3买/3卖 决策支持建议（条件266），
- 用 advice_simulator 逐笔回放：先触止损→亏损单，先触止盈→盈利单，到期→按收盘结算，
- 输出每笔明细与汇总（胜率/平均收益/止损率/止盈率），验证「按建议执行」的期望收益特征。
- 换真实行情时，把 K 线换成实际 closes/highs/lows，并给每条真实买卖点信号生成建议即可。
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from unittest.mock import MagicMock

from easy_tdx.backtest.advice_simulator import simulate_advice_batch
from easy_tdx.chanlun.mmd import _calc_decision_support_enhanced
from easy_tdx.chanlun.types import MMD, MMDType


def _synthetic_klines(n: int = 120, seed: int = 7) -> tuple[list[float], list[float], list[float]]:
    """构造一段震荡上行的合成行情（收盘/最高/最低）。

    前半段横盘整理（让止盈/止损都可能在持有期内触发），
    后半段稳步上行（验证建议在顺势行情中能按止盈落袋）。
    """
    rng = __import__("random").Random(seed)
    closes: list[float] = []
    price = 50.0
    for i in range(n):
        drift = 0.12 if i >= n // 3 else 0.0  # 前 1/3 横盘，之后稳步上行
        wave = 0.6 * math.sin(i / 6.0)  # 让高低点有真实穿透
        price = max(1.0, price + drift + wave * 0.12 + rng.uniform(-0.2, 0.2))
        closes.append(round(price, 3))
    highs = [round(c + abs(0.9 * math.sin(i / 5.0)) + 0.2, 3) for i, c in enumerate(closes)]
    lows = [round(c - abs(0.9 * math.cos(i / 5.0)) - 0.2, 3) for i, c in enumerate(closes)]
    return closes, highs, lows


def _buy3_advice(entry_idx: int, ref_close: float) -> dict:
    """在指定入场点生成一笔 3买 决策支持建议（条件266），入场价贴近信号日收盘。"""
    mmd = MMD(mmd_type=MMDType.BUY_3, msg="3买测试")
    mmd.bi = MagicMock()
    mmd.bi.low = ref_close * 0.98
    mmd.bi.high = ref_close * 1.02
    mmd.zs = MagicMock()
    mmd.zs.zg = ref_close * 1.06
    mmd.zs.zd = ref_close * 0.94
    closes = [ref_close] * 30
    highs = [ref_close * 1.01] * 30
    lows = [ref_close * 0.99] * 30
    a = _calc_decision_support_enhanced(mmd, closes, highs, lows, None, None)
    return {
        "entry_idx": entry_idx,
        "entry_price": a["entry_price"],
        "stop_loss": a["stop_loss"],
        "take_profit_1": a["take_profit_1"],
        "max_hold": 10,
        "direction": "long",
    }


def _sell3_advice(entry_idx: int, ref_close: float) -> dict:
    """在指定入场点生成一笔 3卖（做空）决策支持建议（条件266），入场价贴近信号日收盘。"""
    mmd = MMD(mmd_type=MMDType.SELL_3, msg="3卖测试")
    mmd.bi = MagicMock()
    mmd.bi.low = ref_close * 0.98
    mmd.bi.high = ref_close * 1.02
    mmd.zs = MagicMock()
    mmd.zs.zg = ref_close * 1.06
    mmd.zs.zd = ref_close * 0.94
    closes = [ref_close] * 30
    highs = [ref_close * 1.01] * 30
    lows = [ref_close * 0.99] * 30
    a = _calc_decision_support_enhanced(mmd, closes, highs, lows, None, None)
    return {
        "entry_idx": entry_idx,
        "entry_price": a["entry_price"],
        "stop_loss": a["stop_loss"],  # 做空：止损在上方、止盈在下方
        "take_profit_1": a["take_profit_1"],
        "max_hold": 10,
        "direction": "short",
    }


def main() -> int:
    md = "--md" in sys.argv  # 输出 markdown 报告（供文档引用/无行情环境验证）
    closes, highs, lows = _synthetic_klines(120)

    advices = [_buy3_advice(i, closes[i]) for i in (15, 55, 95)]
    advices += [_sell3_advice(i, closes[i]) for i in (35, 75)]
    report = simulate_advice_batch(highs, lows, closes, advices)

    reason_cn = {"stop": "止损", "tp1": "止盈", "expire": "到期"}
    rows: list[tuple[float, float, float, float, str, float]] = []
    for i, t in enumerate(report["trades"]):
        a = advices[i]
        rows.append(
            (
                a["entry_price"],
                a["stop_loss"],
                a["take_profit_1"],
                t["exit_price"],
                reason_cn.get(t["exit_reason"], t["exit_reason"]),
                t["return_pct"],
            )
        )

    if md:
        print("# V102 建议执行实证报告（合成行情回放）")
        print()
        print(f"行情长度 **{len(closes)}** 根 | 建议笔数 **{len(advices)}**")
        print()
        print("| # | 入场 | 止损 | 止盈1 | 出场价 | 原因 | 收益% |")
        print("|---|-----|-----|------|-------|------|-------|")
        for i, (entry, sl, tp1, exit_price, reason, ret) in enumerate(rows):
            print(
                f"| {i + 1} | {entry:.2f} | {sl:.2f} | {tp1:.2f} | "
                f"{exit_price:.2f} | {reason} | {ret:+.2f} |"
            )
        print()
        print(
            f"**汇总**：胜率 {report['win_rate'] * 100:.0f}% | "
            f"平均收益 {report['avg_return']:+.2f}% | 累计 {report['total_return']:+.2f}%"
        )
        print(
            f"**出场分布**：止损 {report['stop_rate'] * 100:.0f}% / "
            f"止盈 {report['tp_rate'] * 100:.0f}% / 到期 {report['expire_rate'] * 100:.0f}%"
        )
        return 0

    print("=" * 64)
    print("V102 决策支持建议执行实证（合成行情回放）")
    print("=" * 64)
    print(f"行情长度: {len(closes)} 根 | 建议笔数: {len(advices)}")
    print("-" * 64)
    print(f"{'#':>2} {'入场':>8} {'止损':>8} {'止盈1':>8} {'出场价':>8} {'原因':>6} {'收益%':>8}")
    for i, (entry, sl, tp1, exit_price, reason, ret) in enumerate(rows):
        print(
            f"{i + 1:>2} {entry:>8.2f} {sl:>8.2f} "
            f"{tp1:>8.2f} {exit_price:>8.2f} {reason:>6} {ret:>+8.2f}"
        )
    print("-" * 64)
    print(
        f"汇总: 胜率 {report['win_rate'] * 100:.0f}% | 平均收益 {report['avg_return']:+.2f}% | "
        f"累计 {report['total_return']:+.2f}%"
    )
    print(
        f"出场分布: 止损 {report['stop_rate'] * 100:.0f}% | 止盈 {report['tp_rate'] * 100:.0f}% | "
        f"到期 {report['expire_rate'] * 100:.0f}%"
    )
    print("=" * 64)
    print("提示: 把 closes/highs/lows 换成真实行情、advices 换成真实信号的 V102 建议即可复现。")
    print("      --md 输出 Markdown 报告，供文档引用。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
