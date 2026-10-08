"""信号前瞻命中率与模型准确度验证。

目标：让用户通过历史回测验证「模型信号是否真的择时准确」，而不是只看账户盈亏。
对每次实际成交的 BUY/SELL 信号，统计未来 N 根 K 线的前瞻收益与命中率，并与
「随机入场基准」和「同期买入持有基准」对比，回答两个问题：

1. 模型的买卖点是否显著好于随机入场？（超额命中率 = 模型命中率 - 随机命中率）
2. 模型相对涨了就不动的买入持有是否有超额收益？（alpha）

术语：
- 命中（hit）：对 BUY 信号，未来 N 根收益 > 0；对 SELL 信号，未来 N 根收益 < 0
  （卖出是为了避开下跌，因此下跌视为命中）。
- 随机基准：以相同信号数量在全部可入场 bar 上随机采样（可复现 seed），
  统计同一批前瞻窗口的平均命中率与收益，作为「抛硬币择时」的下限参照。
- 前瞻收益：close[idx + h] / close[idx] - 1，h 为持有根数（不含交易成本）。

所有输出为 JSON 兼容的纯 Python 类型（float/int/str/list/dict）。
"""

from __future__ import annotations

from typing import Any, Literal

import numpy as np
import pandas as pd

# 默认前瞻窗口（根数）：1/3/5/10/20 根 K 线后
DEFAULT_HORIZONS: tuple[int, ...] = (1, 3, 5, 10, 20)
# 随机基准采样次数（每窗口）
RANDOM_SAMPLES = 512

# ── "超额命中率"显著性档位阈值（V733 审计命名）────────────────────────
# 这些数字此前**散落 3 处裸写**（0.05 / -0.05 / 0.03），且 0.03 与 0.05 并存，
# 读起来像"写错了却说不清哪个对"。实测两处语义确实不同，故**都命名、不强行
# 合并**，让差异显式化：
#
#   _EXCESS_SIGNIFICANT = 0.05          单标的/单方向判定
#   _EXCESS_PORTFOLIO_SIGNIFICANT = 0.03 组合口径（多标的加权平均）
#     组合跨标的平均后噪声被平滑，故可用更严（更小）的门槛。
#
# ⚠️ 若日后认为两者应统一，改为引用同一常量即可 —— 关键是**别再裸写数字**。
_EXCESS_SIGNIFICANT = 0.05
_EXCESS_PORTFOLIO_SIGNIFICANT = 0.03

# ── 「显著」二字的统计门槛（V736 元审计修复，P0）──────────────────────────
# ⚠️ 本轮实测发现的严重误导（必须记住，别再退回）：
#   修复前 verdict 只做 `excess > 0.05` 的**裸阈值判断**，既不看样本量、
#   也没有任何 p 值 / 置信区间。实测 **n=1 条信号**就能输出
#   「信号命中率显著高于随机入场基准」，而该字符串经
#   web/routers/chanlun.py、stock_pick.py、backtest/engine.py 三处
#   直接显示在 UI「信号准确度」面板上，前端 ChanlunAccuracyPanel.vue
#   还明写「绿色 = 显著优于随机」。用户看到绿色「显著」合理推断是
#   「统计上显著好于抛硬币」——这个推断当时是**错的**。
#
# 故「显著」必须同时满足三条，缺一不可：
#   1. 效应量超过 _EXCESS_SIGNIFICANT（原来的唯一条件）
#   2. 样本量 ≥ _MIN_N_FOR_SIGNIFICANCE（否则噪声主导，见下）
#   3. 通过比例 z 检验（|z| ≥ 1.96，即 95% 置信）
#
# 第 2 条的依据：随机基线本身只用 RANDOM_SAMPLES=512 次抽样，实测其
# 命中率标准差约 1.75 个百分点、95% 区间约 ±3.4pp —— 与 5pp 的效应量
# 门槛只差 2.85 倍。小样本下「超额」极易来自抽样噪声而非真实预测力。
# 取 30 与本项目其他审计脚本的 MIN_N 口径一致。
_MIN_N_FOR_SIGNIFICANCE = 30
# 95% 置信的正态临界值
_Z_95 = 1.96


def _datetime_to_int(arr: np.ndarray) -> np.ndarray:
    """把 datetime 列规整为 YYYYMMDD 整数（与 backtest.strategy 同一口径）。

    Args:
        arr: np.datetime64 / pd.Timestamp / 对象数组

    Returns:
        int64 数组（YYYYMMDD）
    """
    if len(arr) == 0:
        return np.asarray([], dtype=np.int64)
    first = arr[0]
    if isinstance(first, np.datetime64 | pd.Timestamp | pd.Timedelta):
        # 真日期类型 → YYYYMMDD
        return np.asarray(pd.to_datetime(arr).strftime("%Y%m%d").astype(np.int64))
    # 已是数值（int/float，含 YYYYMMDD）原样取整，避免被 pd.to_datetime 误当纳秒
    return np.asarray(arr, dtype=np.float64).astype(np.int64)


def _random_split(n: int, seed: int) -> np.ndarray:
    """可复现的随机索引采样。

    样本数 = min(RANDOM_SAMPLES, n)；可用 bar 不足采样数时直接用全部
    （小样本下全量 = 真实平均基准，避免放回抽样带来的偏差）。
    """
    if n <= 0:
        return np.asarray([], dtype=np.int64)
    if n <= RANDOM_SAMPLES:
        return np.arange(n)
    rng = np.random.default_rng(seed)
    return rng.choice(n, size=RANDOM_SAMPLES, replace=False)


def _horizon_stats(
    fwd: np.ndarray,
) -> dict[str, float]:
    """压缩一个前瞻收益数组为统计字段。

    ⚠️ 单位契约（小数，非百分数）：入参 ``fwd`` 与返回的 avg_return /
    median_return **均为小数** —— 0.0433 表示 +4.33%，不是 4.33。

    与之对接的上游必须同为小数：
    - ``_safe_fwd``（本文件另一处前瞻收益实现；随机基线与 signal 路径共用）
    - ``web/signal_ledger.py::forward_returns``（V736 起统一为小数）
    三者口径一致时 avg_return 与 baseline_avg_return 才可直接相减求超额；
    历史 bug 里台账返回百分数，喂进来后被放大 100 倍。
    hit_rate 是 [0,1] 区间的比率（非百分数）。

    变更单位是**破坏性**的：会让
    ``tests/unit/test_forward_return_unit_contract.py`` 失败（护栏测试）。
    """
    if len(fwd) == 0:
        return {"count": 0, "hit_rate": 0.0, "avg_return": 0.0, "median_return": 0.0}
    return {
        "count": int(len(fwd)),
        "hit_rate": float(np.mean(fwd > 0)),
        "avg_return": float(np.mean(fwd)),
        "median_return": float(np.median(fwd)),
    }


def _safe_fwd(cur: Any, fwd: Any) -> Any:
    """前瞻收益 fwd/cur - 1；价格为 0 时按 -1.0（小数口径下的 -100%）。

    零价格属于退化数据（不应出现在真实行情），按 -1.0 处理可保持数值稳定，
    且不产生 nan 污染后续命中率统计。

    ⚠️ 单位契约（小数，非百分数）：返回值是**小数**，0.0433 == +4.33%。
    哨兵值是 **-1.0**（不是 -100.0），因为它会被喂进同为小数口径的
    ``_horizon_stats`` / 与 baseline_avg_return 相减；写成 -100.0 会让
    「单笔 -100%」在平均值里压过其余样本上百倍。
    """
    cur_arr = np.asarray(cur, dtype=float)
    fwd_arr = np.asarray(fwd, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        denom = np.where(cur_arr == 0, np.nan, cur_arr)
        out = fwd_arr / denom - 1.0
    out = np.nan_to_num(out, nan=-1.0)
    if np.ndim(out) == 0:
        return float(out)
    return out


def _is_significant(
    excess: float,
    n: int,
    baseline_hit_rate: float | None = None,
) -> bool:
    """V736：判定「显著优于随机」——必须同时过效应量、样本量、统计检验三关。

    修复前的实现只做 ``excess > _EXCESS_SIGNIFICANT``，导致 n=1 也能宣称
    「显著优于随机」（实测已复现）。本函数补齐另外两关。

    Args:
        excess: 超额命中率（信号命中率 − 随机基线命中率）
        n: 该窗口的信号样本数
        baseline_hit_rate: 随机基线命中率（用于算标准误；缺失时用 0.5 保守估计）

    Returns:
        是否可宣称「显著」。
    """
    # 第 1 关：效应量（修复前唯一的判断条件）
    if excess <= _EXCESS_SIGNIFICANT:
        return False
    # 第 2 关：样本量。小样本下超额极易来自随机基线的抽样噪声。
    if n < _MIN_N_FOR_SIGNIFICANCE:
        return False
    # 第 3 关：比例 z 检验。H0 = 信号命中率与随机基线无差异。
    p0 = 0.5 if baseline_hit_rate is None else float(baseline_hit_rate)
    # 基线退化到 0/1（例如全涨或全跌的样本）时方差为 0，z 检验失去意义 ——
    # 此时任何 excess 都会算出天文数字的 z 而"显著"。保守处理：不判显著。
    if p0 <= 1e-6 or p0 >= 1 - 1e-6:
        return False
    se = (p0 * (1 - p0) / n) ** 0.5
    if se <= 0:
        return False
    z = excess / se
    return abs(z) >= _Z_95


def _profit_factor(fwd: np.ndarray) -> float:
    """V430: 盈亏比 = 平均盈利 / 平均亏损。

    仅盈利无亏损时取 999.0（有限值，避免 JSON inf）；无样本或无盈利取 0。
    """
    if len(fwd) == 0:
        return 0.0
    gains = fwd[fwd > 0]
    losses = fwd[fwd < 0]
    avg_gain = float(np.mean(gains)) if len(gains) else 0.0
    avg_loss = float(np.mean(np.abs(losses))) if len(losses) else 0.0
    if avg_loss > 0:
        return round(avg_gain / avg_loss, 2)
    if avg_gain > 0:
        return 999.0
    return 0.0


def compute_signal_accuracy(
    df: pd.DataFrame,
    trades: pd.DataFrame,
    horizons: tuple[int, ...] = DEFAULT_HORIZONS,
    strategy_total_return: float | None = None,
    seed: int = 42,
) -> dict[str, Any]:
    """计算一次回测的信号前瞻命中率与准确度验证报告。

    Args:
        df: 回测用 OHLCV DataFrame（须含 datetime/close 列）
        trades: 成交记录 DataFrame（须含 datetime/direction/rejected 列，
            引擎 _trades_to_df 输出即满足）
        horizons: 前瞻窗口（根数）元组
        strategy_total_return: 策略自身总收益率（用于 alpha 对比，可为 None）
        seed: 随机基准采样种子

    Returns:
        dict：{"buy": {...}, "sell": {...}, "benchmark": {...}, "verdict": ...}
        无任何可验证信号时返回 {"buy": None, "sell": None, "benchmark": {...}, "verdict": ...}
    """
    if df is None or len(df) == 0 or trades is None or len(trades) == 0:
        return _empty_report(strategy_total_return)

    if "close" not in df.columns:
        return _empty_report(strategy_total_return, note="数据缺少 close 列")

    closes = df["close"].to_numpy(dtype=float)
    n_bars = len(closes)
    if n_bars < 2:
        return _empty_report(strategy_total_return, note="数据不足 2 根，无法验证前瞻命中率")

    # datetime → bar 索引映射（YYYYMMDD int）
    if "datetime" in df.columns:
        dt_ints = _datetime_to_int(df["datetime"].to_numpy())
    elif "date" in df.columns:
        dt_ints = _datetime_to_int(df["date"].to_numpy())
    else:
        return _empty_report(strategy_total_return, note="数据缺少 datetime/date 列")

    idx_by_dt: dict[int, int] = {}
    for i, dt in enumerate(dt_ints):
        idx_by_dt.setdefault(int(dt), i)

    # 分离 BUY / SELL 已成交信号
    buy_trades = trades[(trades["direction"] == "BUY") & (~trades["rejected"])]
    sell_trades = trades[(trades["direction"] == "SELL") & (~trades["rejected"])]

    # 随机基准：对每个窗口在全部可入场 bar 上采样一次（各窗口独立）
    random_baseline: dict[int, dict[str, float]] = {}
    for h in horizons:
        if n_bars <= h:
            random_baseline[h] = {"count": 0, "hit_rate": 0.0, "avg_return": 0.0}
            continue
        eligible = n_bars - h
        sample_idx = _random_split(eligible, seed)
        fwd = _safe_fwd(closes[sample_idx], closes[sample_idx + h])
        random_baseline[h] = {
            "count": int(len(sample_idx)),
            "hit_rate": float(np.mean(fwd > 0)),
            "avg_return": float(np.mean(fwd)),
        }

    def _signal_stats(
        dir_trades: pd.DataFrame,
        direction: Literal["BUY", "SELL"],
    ) -> dict[str, Any] | None:
        """单方向信号的前瞻统计。"""
        if len(dir_trades) == 0:
            return None
        result: dict[str, Any] = {"signals": int(len(dir_trades)), "horizons": {}}
        # 成交记录的 datetime 在不同路径下可能是 int(YYYYMMDD) 或 Timestamp，
        # 统一规整为 int 便于查索引映射。
        signal_dts = _datetime_to_int(dir_trades["datetime"].to_numpy())
        for h in horizons:
            fwd_list: list[float] = []
            for dt in signal_dts.tolist():
                idx = idx_by_dt.get(int(dt))
                if idx is None or idx + h >= n_bars:
                    continue
                # BUY 持有 N 根；SELL 为空仓避跌，命中 = 期间价格下跌
                raw = _safe_fwd(closes[idx], closes[idx + h])
                fwd_list.append(raw)
            fwd = np.asarray(fwd_list, dtype=float)
            base = random_baseline[h]
            stats = _horizon_stats(fwd)
            # V459: 方向对齐后的盈亏比（BUY 用 fwd，SELL 用 -fwd）
            aligned = -fwd if direction == "SELL" else fwd
            stats["profit_factor"] = _profit_factor(aligned)
            if direction == "SELL":
                # 卖出方向：下跌为命中。随机基准也对齐到下跌方向——
                # 随机空仓「避跌命中」= 随机下跌概率 = 1 - P(上涨)，
                # 随机空仓平均收益 = -随机买入平均收益（V502 修复：旧实现误用
                # 上涨概率作基准，在单边市里高估/低估卖点择时价值）。
                stats["hit_rate"] = float(np.mean(fwd < 0))
                stats["avg_return"] = float(np.mean(-fwd))
                stats["median_return"] = float(np.median(-fwd))
                base_hit = 1.0 - float(base["hit_rate"])
                base_ret = -float(base["avg_return"])
            else:
                base_hit = float(base["hit_rate"])
                base_ret = float(base["avg_return"])
            stats["baseline_hit_rate"] = base_hit
            stats["baseline_avg_return"] = base_ret
            stats["excess_hit_rate"] = (
                float(stats["hit_rate"] - base_hit) if stats["count"] else 0.0
            )
            stats["excess_avg_return"] = (
                float(stats["avg_return"] - base_ret) if stats["count"] else 0.0
            )
            result["horizons"][str(h)] = stats
        return result

    buy_report: dict[str, Any] | None = _signal_stats(buy_trades, "BUY")
    sell_report: dict[str, Any] | None = _signal_stats(sell_trades, "SELL")

    # 基准：同期买入持有总收益
    buy_hold_return = float(closes[-1] / closes[0] - 1.0) if closes[0] != 0 else 0.0
    benchmark: dict[str, float] = {"buy_hold_return": buy_hold_return}
    if strategy_total_return is not None:
        benchmark["strategy_return"] = strategy_total_return
        benchmark["alpha"] = float(strategy_total_return - buy_hold_return)

    verdict = _build_verdict(buy_report, buy_hold_return)

    return {
        "buy": buy_report,
        "sell": sell_report,
        "benchmark": benchmark,
        "verdict": verdict,
    }


def _build_verdict(
    buy_report: dict[str, Any] | None,
    buy_hold_return: float,
) -> str:
    """根据 5 根窗口（若存在）生成一句可读结论。"""
    if buy_report is None:
        return "无买入成交记录，无法验证择时准确度"
    horizons = buy_report.get("horizons", {})
    h5 = horizons.get("5") or horizons.get("3") or horizons.get("10")
    if not h5 or h5.get("count", 0) == 0:
        return "买入信号不足，无法形成可靠结论（样本过少）"
    excess = float(h5.get("excess_hit_rate", 0.0))
    avg = float(h5.get("avg_return", 0.0))
    n = int(h5.get("count", 0))
    parts = [f"买入信号 {n} 个"]
    baseline = h5.get("baseline_hit_rate")
    significant = _is_significant(excess, n, baseline)
    if n < _MIN_N_FOR_SIGNIFICANCE:
        # V736：样本不足时不许用「显著」二字（实测 n=1 曾判「显著高于」）
        grade = (
            "命中率与随机入场基本相当（择时贡献有限）"
            if excess > -_EXCESS_SIGNIFICANT
            else "信号命中率低于随机入场（可能有反向择时风险）"
        )
        grade += f"（样本仅 {n} 个，不足以判断显著性）"
    elif significant:
        grade = "信号命中率显著高于随机入场基准"
    elif excess > 0:
        grade = "信号命中率略高于随机入场基准"
    elif excess > -_EXCESS_SIGNIFICANT:
        grade = "命中率与随机入场基本相当（择时贡献有限）"
    else:
        grade = "信号命中率低于随机入场（可能有反向择时风险）"
    parts.append(grade)
    if buy_hold_return != 0:
        parts.append(f"同期买入持有 {buy_hold_return:+.2%}")
    parts.append(f"5根前瞻均值 {avg:+.2%}")
    return "；".join(parts) + "。"


def _empty_report(
    strategy_total_return: float | None,
    note: str = "",
) -> dict[str, Any]:
    """无可验证数据时的空报告。"""
    benchmark: dict[str, float] = {}
    if strategy_total_return is not None:
        benchmark["strategy_return"] = strategy_total_return
        benchmark["buy_hold_return"] = 0.0
        benchmark["alpha"] = strategy_total_return
    report: dict[str, Any] = {
        "buy": None,
        "sell": None,
        "benchmark": benchmark,
        "note": note,
    }
    report["verdict"] = note or "无成交记录，无法验证择时准确度"
    return report


# ── 按信号类型分组的准确度验证（缠论买卖点等） ───────────────────────────────


def _classify_direction(sig_type: str) -> str:
    """按类型名推断方向：含 buy 视为买点（上涨为命中），否则视为卖点（下跌为命中）。"""
    return "BUY" if "buy" in sig_type.lower() else "SELL"


def _signal_type_stats(
    sig_type: str,
    idx_list: list[int],
    closes: np.ndarray,
    horizons: tuple[int, ...],
    baseline: dict[int, dict[str, float]],
) -> dict[str, Any]:
    """单个信号类型的前瞻统计。

    V722: 前瞻收益计算统一走 web/signal_ledger.py（唯一实现），
    accuracy 审计与本面板共用同一口径，防止两处各算各的漂移。
    """
    direction = _classify_direction(sig_type)
    out: dict[str, Any] = {
        "type": sig_type,
        "signals": len(idx_list),
        "direction": direction,
        "horizons": {},
    }
    # 统一台账：逐信号逐窗口的前瞻收益记录（方向对齐后）
    from easy_tdx.web.signal_ledger import signal_returns

    ledger = signal_returns(
        closes,
        [{"type": sig_type, "bar_index": idx} for idx in idx_list if idx is not None],
        horizons=horizons,
    )
    for h in horizons:
        recs = [r for r in ledger if r.horizon == h]
        fwd_list = [float(r.raw_ret_pct or 0.0) for r in recs]
        fwd = np.asarray(fwd_list, dtype=float)
        stats = _horizon_stats(fwd)
        # V430: 方向对齐后的盈亏比（BUY 用 fwd，SELL 用 -fwd）
        aligned = -fwd if direction == "SELL" else fwd
        stats["profit_factor"] = _profit_factor(aligned)
        if direction == "SELL" and len(fwd) > 0:
            stats["hit_rate"] = float(np.mean(fwd < 0))
            stats["avg_return"] = float(np.mean(-fwd))
            stats["median_return"] = float(np.median(-fwd))
        base = baseline[h]
        # V503: 卖出基准对齐下跌方向（同 compute_signal_accuracy 的 V502 修复）
        if direction == "SELL":
            base_hit = 1.0 - float(base["hit_rate"])
            base_ret = -float(base["avg_return"])
        else:
            base_hit = float(base["hit_rate"])
            base_ret = float(base["avg_return"])
        stats["baseline_hit_rate"] = base_hit
        stats["baseline_avg_return"] = base_ret
        stats["excess_hit_rate"] = float(stats["hit_rate"] - base_hit) if stats["count"] else 0.0
        stats["excess_avg_return"] = (
            float(stats["avg_return"] - base_ret) if stats["count"] else 0.0
        )
        out["horizons"][str(h)] = stats
    out["verdict"] = _signal_type_verdict(out)
    return out


def _signal_type_verdict(report: dict[str, Any]) -> str:
    """单类型一句结论（取 5 根窗口，缺则回退 3/10）。

    V432: 结合盈亏比 profit_factor——命中率优但 PF<1 时提示「盈亏比差」。
    """
    horizons = report.get("horizons", {})
    h5 = horizons.get("5") or horizons.get("3") or horizons.get("10")
    if not h5 or h5.get("count", 0) == 0:
        return "样本不足，无法可靠评估"
    excess = float(h5.get("excess_hit_rate", 0.0))
    pf = float(h5.get("profit_factor", 0.0))
    n = int(h5.get("count", 0))
    direction = report.get("direction", "BUY")
    verb = "买入" if direction == "BUY" else "卖出"
    pf_note = f"PF={pf:.2f}" if pf > 0 else ""
    # V736：n 不足或 z 检验不过时，一律降级为「略优/相当」，不许说「显著」
    significant = _is_significant(excess, n, h5.get("baseline_hit_rate"))
    if significant:
        if pf_note and pf < 1.0:
            return (
                verb
                + "点显著优于随机但盈亏比差（+"
                + f"{excess:.1%}"
                + "，"
                + pf_note
                + "，n="
                + str(n)
                + "）"
            )
        return verb + "点显著优于随机（+" + f"{excess:.1%}" + "，n=" + str(n) + "）"
    if excess > _EXCESS_SIGNIFICANT:
        # 效应量够但样本/z 检验不够 —— 明确说明，而不是含糊说「略优」
        return (
            verb
            + "点优于随机但样本不足，尚不能称显著（+"
            + f"{excess:.1%}"
            + "，n="
            + str(n)
            + f"，需 n≥{_MIN_N_FOR_SIGNIFICANCE} 且通过 z 检验）"
        )
    if excess > 0:
        if pf_note and pf < 1.0:
            return (
                verb
                + "点略优于随机但盈亏比差（+"
                + f"{excess:.1%}"
                + "，"
                + pf_note
                + "，n="
                + str(n)
                + "）"
            )
        return verb + "点略优于随机（+" + f"{excess:.1%}" + "，n=" + str(n) + "）"
    if excess > -_EXCESS_SIGNIFICANT:
        return verb + "点与随机相当（" + f"{excess:+.1%}" + "，n=" + str(n) + "）"
    return verb + "点弱于随机（" + f"{excess:+.1%}" + "，n=" + str(n) + "）"


def compute_signal_accuracy_by_type(
    closes: list[float] | np.ndarray,
    signals: list[dict[str, Any]],
    horizons: tuple[int, ...] = DEFAULT_HORIZONS,
    seed: int = 42,
) -> dict[str, Any]:
    """按信号类型分组的前瞻命中率验证（适用于缠论买卖点等带类型的信号）。

    与 compute_signal_accuracy 的区别：输入直接是带类型的信号列表
    （每条含 type 与 bar_index），按类型（如 1buy/2buy/3buy/1sell/…）
    分组，对每个类型统计未来 N 根前瞻收益、命中率，并与随机入场基准对比，
    回答「哪类信号真的准」。

    Args:
        closes: 收盘价序列（与 K 线一一对应）
        signals: 信号列表，每条为 {"type": str, "bar_index": int|None}
        horizons: 前瞻窗口（根数）
        seed: 随机基准采样种子

    Returns:
        dict：{"by_type": {类型: {signals, direction, horizons, verdict}},
              "ranking": [按5根超额命中率降序的类型摘要],
              "summary": 一句总体结论}
    """
    closes_arr = np.asarray(closes, dtype=float)
    n_bars = len(closes_arr)
    if n_bars < 2 or not signals:
        return {"by_type": {}, "ranking": [], "summary": "无信号或数据不足，无法验证"}

    # 随机基准（每窗口）
    baseline: dict[int, dict[str, float]] = {}
    for h in horizons:
        if n_bars <= h:
            baseline[h] = {"count": 0, "hit_rate": 0.0, "avg_return": 0.0}
            continue
        eligible = n_bars - h
        sample_idx = _random_split(eligible, seed)
        fwd = _safe_fwd(closes_arr[sample_idx], closes_arr[sample_idx + h])
        baseline[h] = {
            "count": int(len(sample_idx)),
            "hit_rate": float(np.mean(fwd > 0)),
            "avg_return": float(np.mean(fwd)),
        }

    # 按类型分组
    grouped: dict[str, list[int]] = {}
    for sig in signals:
        sig_type = str(sig.get("type", "unknown"))
        bar_index = sig.get("bar_index")
        if bar_index is None:
            continue
        grouped.setdefault(sig_type, []).append(int(bar_index))

    by_type: dict[str, Any] = {}
    for sig_type, idx_list in grouped.items():
        by_type[sig_type] = _signal_type_stats(sig_type, idx_list, closes_arr, horizons, baseline)

    # 排名：按 5 根窗口超额命中率降序（缺窗口按 3/10）
    def _key(item: tuple[str, dict[str, Any]]) -> float:
        h5 = item[1]["horizons"].get("5")
        if not h5 or h5.get("count", 0) == 0:
            return -999.0
        return float(h5.get("excess_hit_rate", 0.0))

    ranking: list[dict[str, Any]] = []
    for sig_type, report in sorted(by_type.items(), key=_key, reverse=True):
        h5 = report["horizons"].get("5") or report["horizons"].get("3")
        ranking.append(
            {
                "type": sig_type,
                "direction": report["direction"],
                "signals": report["signals"],
                "excess_hit_rate": float(h5.get("excess_hit_rate", 0.0)) if h5 else 0.0,
                "avg_return": float(h5.get("avg_return", 0.0)) if h5 else 0.0,
                "hit_rate": float(h5.get("hit_rate", 0.0)) if h5 else 0.0,
                "profit_factor": float(h5.get("profit_factor", 0.0)) if h5 else 0.0,
                "verdict": report["verdict"],
            }
        )

    summary = _build_type_summary(by_type)
    return {"by_type": by_type, "ranking": ranking, "summary": summary}


def _build_type_summary(by_type: dict[str, Any]) -> str:
    """从各类型报告中挑出最强买点/卖点，生成一句总体结论。"""
    best_buy: dict[str, Any] | None = None
    best_sell: dict[str, Any] | None = None
    for sig_type, report in by_type.items():
        h5 = report["horizons"].get("5") or report["horizons"].get("3")
        if not h5 or h5.get("count", 0) == 0:
            continue
        excess = float(h5.get("excess_hit_rate", 0.0))
        if report["direction"] == "BUY":
            if best_buy is None or excess > float(
                best_buy["horizons"].get("5", {}).get("excess_hit_rate", 0.0)
            ):
                best_buy = report
        else:
            if best_sell is None or excess > float(
                best_sell["horizons"].get("5", {}).get("excess_hit_rate", 0.0)
            ):
                best_sell = report

    parts: list[str] = []
    if best_buy:
        h5 = best_buy["horizons"].get("5") or best_buy["horizons"].get("3")
        pf = float(h5.get("profit_factor", 0.0))
        # V473: PF >= 999（仅盈利）显示 ∞，与前端 fmtPf 一致
        pf_str = "∞" if pf >= 999 else f"{pf:.2f}"
        pf_note = f"，盈亏比 {pf_str}" if pf > 0 else ""
        parts.append(
            "最强买点 "
            + best_buy.get("type", "?")
            + "（5根命中 "
            + f"{h5['hit_rate']:.0%}"
            + "，超额 "
            + f"{h5['excess_hit_rate']:+.1%}"
            + pf_note
            + "）"
        )
    if best_sell:
        h5 = best_sell["horizons"].get("5") or best_sell["horizons"].get("3")
        pf = float(h5.get("profit_factor", 0.0))
        pf_str = "∞" if pf >= 999 else f"{pf:.2f}"
        pf_note = f"，盈亏比 {pf_str}" if pf > 0 else ""
        parts.append(
            "最强卖点 "
            + best_sell.get("type", "?")
            + "（5根命中 "
            + f"{h5['hit_rate']:.0%}"
            + "，超额 "
            + f"{h5['excess_hit_rate']:+.1%}"
            + pf_note
            + "）"
        )
    if not parts:
        return "各类型样本均不足，无法验证可靠命中率"
    return "；".join(parts) + "。"


# ── 组合/多标的聚合准确度验证 ───────────────────────────────────────────────


def _symbol_accuracy_row(
    key: str,
    result: Any,
    allocation: float = 0.0,
) -> dict[str, Any]:
    """从单个标的的 BacktestResult（或其 to_dict）提取准确度摘要行。"""
    sa = getattr(result, "signal_accuracy", None)
    if sa is None and isinstance(result, dict):
        sa = result.get("signal_accuracy")
    perf = getattr(result, "performance", None)
    if perf is None and isinstance(result, dict):
        perf = result.get("performance") or {}

    hit_rate: float | None = None
    baseline_hit: float | None = None
    if sa:
        buy = (sa.get("buy") if isinstance(sa, dict) else None) or {}
        horizons = (buy.get("horizons") if isinstance(buy, dict) else None) or {}
        for h in ("5", "3", "10"):
            stats = horizons.get(h)
            if stats and stats.get("count", 0) > 0:
                hit_rate = float(stats["hit_rate"])
                baseline_hit = float(stats.get("baseline_hit_rate", 0.0))
                break

    def _g(key_: str, default: float = 0.0) -> float:
        if perf and isinstance(perf, dict):
            v = perf.get(key_)
            if v is not None:
                try:
                    return float(v)
                except (TypeError, ValueError):
                    return default
        return default

    row: dict[str, Any] = {
        "symbol": str(key),
        "allocation": allocation,
        "total_return": _g("total_return"),
        "win_rate": _g("win_rate"),
        "sharpe": _g("sharpe"),
        "max_drawdown": _g("max_drawdown"),
        "trades": int(_g("total_trades")),
        "hit_rate": hit_rate,
        "baseline_hit_rate": baseline_hit,
        "excess_hit_rate": (hit_rate - baseline_hit)
        if hit_rate is not None and baseline_hit is not None
        else None,
    }
    # V110: 单标的模型可信度（V101 机制，无分段稳健性时中性参与）
    try:
        from easy_tdx.backtest.model_trust import compute_model_trust

        mt = getattr(result, "model_trust", None)
        if mt is None and isinstance(result, dict):
            mt = result.get("model_trust")
        if mt is None:
            mt = compute_model_trust(perf, sa, None)
        if mt:
            row["trust_score"] = float(mt.get("score", 0.0))
            row["trust_grade"] = str(mt.get("grade", ""))
        else:
            row["trust_score"] = None
            row["trust_grade"] = None
    except Exception:  # noqa: BLE001
        row["trust_score"] = None
        row["trust_grade"] = None
    return row


def aggregate_portfolio_accuracy(
    individual_results: dict[str, Any],
    allocations: dict[str, float] | None = None,
    alpha_key: str = "alpha",
) -> dict[str, Any]:
    """聚合组合回测中逐标的的准确度与绩效，生成组合级验证报告。

    Args:
        individual_results: {symbol: BacktestResult 或 result.to_dict()}，
            每只标的的独立回测结果（V95 起 signal_accuracy 已随结果输出）。
        allocations: 资金分配比例 {symbol: 比例}；缺省按均等处理。
        alpha_key: 绩效字段中代表超额收益的键（组合场景可后续补充）。

    Returns:
        dict：{"symbols": [逐标摘要行], "portfolio": {...}, "verdict": str}
        无有效标的数据时返回最小报告。
    """
    if not individual_results:
        return {"symbols": [], "portfolio": {}, "verdict": "无标的，无法聚合准确度"}

    n = len(individual_results)
    rows: list[dict[str, Any]] = []
    for key, result in individual_results.items():
        alloc = (allocations or {}).get(str(key), 1.0 / n)
        rows.append(_symbol_accuracy_row(str(key), result, alloc))

    # 组合级汇总（按资金分配加权）
    def _weighted(getter: Any) -> float:
        vals = [(r["allocation"], getter(r)) for r in rows if getter(r) is not None]
        if not vals:
            return 0.0
        w = sum(a for a, _ in vals)
        return sum(a * v for a, v in vals) / w if w else 0.0

    hit_rows = [r for r in rows if r["hit_rate"] is not None]
    portfolio = {
        "symbols": len(rows),
        "symbols_with_accuracy": len(hit_rows),
        "avg_hit_rate": _weighted(lambda r: r["hit_rate"]),
        "avg_baseline_hit_rate": _weighted(lambda r: r["baseline_hit_rate"]),
        "avg_excess_hit_rate": _weighted(lambda r: r["excess_hit_rate"]),
        "avg_win_rate": _weighted(lambda r: r["win_rate"]),
        "avg_total_return": _weighted(lambda r: r["total_return"]),
        "avg_sharpe": _weighted(lambda r: r["sharpe"]),
        "positive_symbols": sum(1 for r in rows if r["total_return"] > 0),
        "hit_above_baseline": sum(
            1 for r in hit_rows if r["excess_hit_rate"] is not None and r["excess_hit_rate"] > 0
        ),
    }

    verdict = _build_portfolio_verdict(portfolio)
    return {"symbols": rows, "portfolio": portfolio, "verdict": verdict}


def _build_portfolio_verdict(portfolio: dict[str, Any]) -> str:
    """生成组合级准确度结论。"""
    n = int(portfolio["symbols"])
    if n == 0:
        return "无标的，无法评估"
    hit_n = int(portfolio.get("symbols_with_accuracy", 0))
    parts = [f"组合 {n} 只标的"]
    if hit_n > 0:
        avg_excess = float(portfolio.get("avg_excess_hit_rate", 0.0))
        avg_hit = float(portfolio.get("avg_hit_rate", 0.0))
        parts.append(f"{hit_n} 只有命中率数据")
        parts.append(f"加权平均 5 根命中率 {avg_hit:.1%}")
        if avg_excess > _EXCESS_PORTFOLIO_SIGNIFICANT:
            parts.append("整体命中率高于随机入场基准，模型择时具备参考价值")
        elif avg_excess > 0:
            parts.append("整体命中率略高于随机基准，择时贡献为正但有限")
        else:
            parts.append("整体命中率不高于随机基准，择时贡献有限")
    pos = int(portfolio.get("positive_symbols", 0))
    parts.append(f"{pos}/{n} 只标的正收益")
    above = int(portfolio.get("hit_above_baseline", 0))
    if hit_n > 0:
        parts.append(f"{above}/{hit_n} 只命中率高于随机基准")
    return "；".join(parts) + "。"
