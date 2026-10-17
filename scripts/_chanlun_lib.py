"""缠论回测的共用工具：原文口径策略构造 + trades → 逐笔配对。

## 为什么需要
曾经的 ``ChanlunPairStrategy`` 自带 ``pair_log``（逐笔买卖点配对），
多个审计脚本直接读它。该策略因「区间套过滤用 level_synth 合成数据，
是伪区间套不符合原文」被**整体移除**，缠论策略收敛为单一
``ChanlunStrategy``（``stop_loss_pct`` / ``take_profit_pct`` 设为 0
即得「日线买点进 → 日线卖点出」的原文口径）。

本模块提供两个替代：

- :func:`make_original_strategy` —— 构造原文口径的 chanlun 策略；
- :func:`pairs_from_trades` —— 从引擎 ``trades`` 自行拆出配对记录，
  字段与旧 ``pair_log`` 保持一致（``entry_type`` / ``exit_type`` /
  ``holding_bars`` / ``entry_price`` / ``exit_price`` / ``pnl_pct``）。

配对依据：引擎 ``trades.tag`` 沿用开仓信号类型（平仓时附
``->stop_loss`` / ``->take_profit`` 归因后缀），据此拆出入场/出场类型。
"""

from __future__ import annotations

import pandas as pd

from easy_tdx.backtest.strategies.chanlun import ChanlunStrategy

# 真实缠论卖点类型（用于区分「卖点出场」与「止损止盈/兜底强平」）
REAL_SELL_TYPES = ("1sell", "2sell", "2sell_s", "3sell")


def make_original_strategy(**kwargs):
    """构造「缠论原文口径」策略：买卖点信号进出，不设百分比止损止盈。

    Args:
        **kwargs: 透传给 ``ChanlunStrategy``（如 ``use_3sell=False``）。

    Returns:
        ChanlunStrategy: ``stop_loss_pct=take_profit_pct=0`` 的策略实例。
    """
    base = {"stop_loss_pct": 0.0, "take_profit_pct": 0.0}
    base.update(kwargs)
    return ChanlunStrategy(**base)


def pairs_from_trades(result) -> list[dict]:
    """把引擎回测结果拆成逐笔配对（对齐旧 ``pair_log`` 的字段）。

    Args:
        result: ``BacktestEngine.run(df)`` 的返回值（含 ``trades``）。

    Returns:
        list[dict]: 每项含 ``entry_type`` / ``exit_type`` / ``entry_bar`` /
            ``exit_bar`` / ``holding_bars`` / ``entry_price`` /
            ``exit_price`` / ``pnl_pct``。
    """
    t = getattr(result, "trades", None)
    if t is None or len(t) == 0:
        return []

    pairs: list[dict] = []
    entry_type = ""
    entry_bar = 0
    entry_price = 0.0
    for i, row in enumerate(t.itertuples(index=False)):
        tag = str(getattr(row, "tag", "") or "")
        direction = str(row.direction)
        if direction == "BUY":
            entry_type = tag.split("->")[0] or "?"
            entry_bar = i
            entry_price = float(row.price)
            continue
        if direction == "SELL" and entry_type:
            # 平仓 tag 可能是 "1sell"（卖点）或 "1buy->stop_loss"（归因）
            exit_type = tag.split("->")[0] if "->" in tag else tag
            exit_type = exit_type or "close"
            pairs.append(
                {
                    "entry_type": entry_type,
                    "exit_type": exit_type,
                    "entry_bar": entry_bar,
                    "exit_bar": i,
                    "holding_bars": i - entry_bar,
                    "entry_price": entry_price,
                    "exit_price": float(row.price),
                    "pnl_pct": (float(row.price) / entry_price - 1) * 100
                    if entry_price
                    else 0.0,
                }
            )
            entry_type = ""
    return pairs


def load_daily_df(path) -> pd.DataFrame:
    """读 audit_data 的日线 JSON 并解析 datetime（审计脚本通用）。"""
    import json

    df = pd.DataFrame(json.loads(path.read_text(encoding="utf-8")))
    df["datetime"] = pd.to_datetime(df["datetime"])
    return df


def drop_unknown_params(entry, params: dict) -> dict:
    """剔除策略 schema 里不存在的参数。

    历史参数探索脚本（optimize_round2/3、final_verification、backtest_seg_mmd）
    曾按已废弃的 ``chanlun_pair`` 写死参数（``hold_in_higher_uptrend`` /
    ``exit_trailing_stop_pct`` / ``allow_pyramid`` / ``seg_divergence_rate`` …）。
    ``ParametrizedStrategy.__init__`` 对未知参数抛 ``ValueError``，
    故这里在 build 前过滤，只传当前策略 schema 支持的键。

    Args:
        entry: ``RegisteredStrategy``（注册表条目）。
        params: 原始参数字典。

    Returns:
        dict: 仅含 schema 支持的键（其余原样保留的值）。
    """
    declared = {p.name for p in entry.params}
    kept = {k: v for k, v in params.items() if k in declared}
    dropped = sorted(set(params) - declared)
    if dropped:
        print(f"⚠️ 已忽略当前策略不支持的参数: {dropped}")
    return kept
