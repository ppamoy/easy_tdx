"""缠论分析路由。"""

from __future__ import annotations

from typing import Any

import pandas as pd

from fastapi import APIRouter, Depends
from pydantic import Field

from easy_tdx.web.convert import category_from_str, market_from_str
from easy_tdx.web.deps import get_client
from easy_tdx.web.schemas import ChanlunRequest

router = APIRouter(tags=["chanlun"])


def _to_json_safe(obj: Any) -> Any:
    """递归将 numpy 类型转换为 JSON 可序列化的 Python 原生类型。"""
    import numpy as np
    if isinstance(obj, dict):
        return {k: _to_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_json_safe(item) for item in obj]
    if isinstance(obj, np.bool_):
        return bool(obj)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    return obj



def build_train_session_payload(result: Any, df: pd.DataFrame, category: str) -> dict[str, Any]:
    """把缠论分析结果组装成训练会话负载（纯函数，可单测）。

    - bars：K 线（与 /bars 同列）
    - bis/xds/zss/mmds/fractals/bcs/boll：完整结构
    - candidates：候选点（买卖点信号 + 采样分型干扰项），供逐步揭示提问
    - mmd_outcomes：每个买卖点的信号后 5/10/20 日收益（复盘验证）
    """
    # K 线（与 /bars 一致的列）
    _date_col = "date" if "date" in df.columns else "datetime"
    bars: list[dict[str, Any]] = []
    for _i, row in df.iterrows():
        dt = row[_date_col]
        bars.append({
            "datetime": str(dt)[:19].replace(" ", "T"),
            "open": round(float(row["open"]), 3),
            "close": round(float(row["close"]), 3),
            "high": round(float(row["high"]), 3),
            "low": round(float(row["low"]), 3),
            "vol": float(row.get("vol", 0) or 0),
            "amount": float(row.get("amount", 0) or 0),
        })

    # 结构数据（复用 analyze 的序列化）
    d = result.to_dict()
    d["fractals"] = [
        {
            "fx_type": fx.fx_type.value,
            "date": result._fmt_dt(fx.k.date),
            "val": round(fx.val, 2),
            "index": fx.index,
        }
        for fx in result.fractals
    ]
    if result.boll:
        d["boll"] = {
            "upper": [round(x, 2) for x in result.boll.upper[-100:]],
            "mid": [round(x, 2) for x in result.boll.mid[-100:]],
            "lower": [round(x, 2) for x in result.boll.lower[-100:]],
            "width": [round(x, 2) for x in result.boll.width[-100:]],
            "percent_b": [round(x, 2) for x in result.boll.percent_b[-100:]],
            "latest_upper": round(result.boll.latest_upper, 2),
            "latest_mid": round(result.boll.latest_mid, 2),
            "latest_lower": round(result.boll.latest_lower, 2),
            "latest_percent_b": round(result.boll.latest_percent_b, 2),
            "latest_width": round(result.boll.latest_width, 4),
        }
    else:
        d["boll"] = None

    # 候选点：每个买卖点一个（kind=mmd），外加采样分型干扰项（kind=fractal）
    mmd_cands: list[dict[str, Any]] = []
    for mmd in result.mmds:
        if not mmd.bi:
            continue
        k_idx = mmd.bi.end.k.k_index
        mmd_cands.append({
            "index": k_idx,
            "date": result._fmt_dt(mmd.bi.end.k.date),
            "kind": "mmd",
            "fx_type": None,
            "signal": {
                "type": mmd.mmd_type.value,
                "confidence": round(mmd.confidence, 2),
                "grade": getattr(getattr(mmd, "quality", None), "grade", None),
            },
        })
    mmd_idx_set = {c["index"] for c in mmd_cands}
    fx_cands: list[dict[str, Any]] = []
    for fx in result.fractals:
        k_idx = fx.k.k_index
        if any(abs(k_idx - m) <= 3 for m in mmd_idx_set):
            continue
        fx_cands.append({
            "index": k_idx,
            "date": result._fmt_dt(fx.k.date),
            "kind": "fractal",
            "fx_type": fx.fx_type.value,
            "signal": None,
        })
    # 均匀采样干扰项：总数（信号+干扰）控制在 ~40
    target_total = 40
    distract_max = max(target_total - len(mmd_cands), 0)
    if len(fx_cands) > distract_max:
        step = len(fx_cands) / distract_max
        fx_cands = [fx_cands[int(i * step)] for i in range(distract_max)]
    candidates = sorted(mmd_cands + fx_cands, key=lambda c: c["index"])

    # 买卖点信号后 N 日收益
    closes = [k.close for k in result.klines]

    def _ret_from(idx: int, n: int) -> float | None:
        if idx is None or idx < 0 or idx >= len(closes):
            return None
        end = idx + n
        if end >= len(closes):
            return None
        base = closes[idx]
        if not base:
            return None
        return round((closes[end] / base - 1) * 100, 2)

    mmd_outcomes: list[dict[str, Any]] = []
    for mmd in result.mmds:
        if not mmd.bi:
            continue
        k_idx = mmd.bi.end.k.k_index
        outcomes: dict[str, Any] = {
            "type": mmd.mmd_type.value,
            "date": result._fmt_dt(mmd.bi.end.k.date),
            "price": round(result.klines[k_idx].close, 2) if 0 <= k_idx < len(result.klines) else None,
            "ret_5d": _ret_from(k_idx, 5),
            "ret_10d": _ret_from(k_idx, 10),
            "ret_20d": _ret_from(k_idx, 20),
            "max_5d": None,
            "min_5d": None,
        }
        if 0 <= k_idx < len(closes):
            base = closes[k_idx]
            if base:
                win = closes[k_idx : k_idx + 6]
                if win:
                    outcomes["max_5d"] = round((max(win) / base - 1) * 100, 2)
                    outcomes["min_5d"] = round((min(win) / base - 1) * 100, 2)
        mmd_outcomes.append(outcomes)

    return _to_json_safe({
        "code": result.code,
        "frequency": result.frequency,
        "category": category,
        "bars": bars,
        "bis": d.get("bis", []),
        "xds": d.get("xds", []),
        "zss": d.get("zss", []),
        "mmds": d.get("mmds", []),
        "fractals": d.get("fractals", []),
        "bcs": d.get("bcs", []),
        "boll": d.get("boll"),
        "candidates": candidates,
        "mmd_outcomes": mmd_outcomes,
    })


@router.post("/chanlun/analyze")
async def chanlun_analyze(
    req: ChanlunRequest,
    client: Any = Depends(get_client),
) -> dict[str, Any]:
    """执行缠论分析。

    自动从 TDX 服务器获取 K 线数据，运行完整缠论计算管道，
    返回笔、中枢、线段、买卖点、背驰、分型等分析结果。
    """
    from easy_tdx.chanlun import ChanlunAnalyser

    # 1. Fetch kline data
    df = await client.get_security_bars(
        market_from_str(req.market),
        req.code,
        category_from_str(req.category),
        req.start,
        req.count,
    )

    # 2. Run chanlun analysis
    symbol = f"{req.market}{req.code}"
    frequency_map: dict[str, str] = {
        "MIN_1": "1min",
        "MIN_5": "5min",
        "MIN_15": "15min",
        "MIN_30": "30min",
        "MIN_60": "60min",
        "DAY": "daily",
        "WEEK": "weekly",
        "MONTH": "monthly",
        "YEAR": "yearly",
    }
    freq = frequency_map.get(req.category.upper(), req.category)
    analyser = ChanlunAnalyser(code=symbol, frequency=freq)
    result = analyser.process_klines(df)

    # 3. 返回完整分析结果，包括分型数据和BOLL
    d = result.to_dict()

    # 添加分型数据
    d["fractals"] = [
        {
            "fx_type": fx.fx_type.value,
            "date": result._fmt_dt(fx.k.date),
            "val": round(fx.val, 2),
            "index": fx.index,
        }
        for fx in result.fractals
    ]

    # 添加BOLL数据
    if result.boll:
        n = len(result.boll.upper)
        d["boll"] = {
            "upper": [round(x, 2) for x in result.boll.upper[-100:]],
            "mid": [round(x, 2) for x in result.boll.mid[-100:]],
            "lower": [round(x, 2) for x in result.boll.lower[-100:]],
            "width": [round(x, 2) for x in result.boll.width[-100:]],
            "percent_b": [round(x, 2) for x in result.boll.percent_b[-100:]],
            "latest_upper": round(result.boll.latest_upper, 2),
            "latest_mid": round(result.boll.latest_mid, 2),
            "latest_lower": round(result.boll.latest_lower, 2),
            "latest_percent_b": round(result.boll.latest_percent_b, 2),
            "latest_width": round(result.boll.latest_width, 4),
        }

    return d


class ChanlunMultiLevelRequest(ChanlunRequest):
    """多级别缠论分析请求。"""

    low_level: str = Field(default="MIN_30", description="低级别周期（如 MIN_30, MIN_5）")


@router.post("/chanlun/multi-level")
async def chanlun_multi_level(
    req: ChanlunMultiLevelRequest,
    client: Any = Depends(get_client),
) -> dict[str, Any]:
    """多级别缠论分析：同时分析高级别和低级别，返回一致性评分。

    用于区间套判断：大级别背驰在小级别先确认。
    """
    from easy_tdx.chanlun import ChanlunAnalyser
    from easy_tdx.chanlun.multi_level import MultiLevelAnalyser

    frequency_map: dict[str, str] = {
        "MIN_1": "1min",
        "MIN_5": "5min",
        "MIN_15": "15min",
        "MIN_30": "30min",
        "MIN_60": "60min",
        "DAY": "daily",
        "WEEK": "weekly",
    }
    high_freq = frequency_map.get(req.category.upper(), "daily")
    low_freq = frequency_map.get(req.low_level.upper(), "30min")

    symbol = f"{req.market}{req.code}"

    # 获取高级别数据
    df_high = await client.get_security_bars(
        market_from_str(req.market),
        req.code,
        category_from_str(req.category),
        req.start,
        req.count,
    )
    # 获取低级别数据（需要覆盖高级别的时间范围，否则最新高级别笔的低级别走势为空）
    # 每自然日对应的低级别 K 线数（A股一天约4小时交易时段）
    _bars_per_day = {
        "MIN_1": 240, "MIN_5": 48, "MIN_15": 16, "MIN_30": 8, "MIN_60": 4,
    }
    low_bars_per_day = _bars_per_day.get(req.low_level.upper(), 8)
    try:
        if df_high is not None and len(df_high) > 0:
            # 用高级别实际时间跨度估算低级别K线数量
            _date_col = "date" if "date" in df_high.columns else "datetime"
            _first = pd.to_datetime(df_high[_date_col].iloc[0])
            _last = pd.to_datetime(df_high[_date_col].iloc[-1])
            span_days = max((_last - _first).days, 1)
            trading_days = int(span_days / 7 * 5) + 1
            low_count = int(min(trading_days * low_bars_per_day + 200, 10000))
        else:
            low_count = int(min(req.count * low_bars_per_day + 200, 10000))
    except Exception:
        low_count = int(min(req.count * low_bars_per_day + 200, 10000))
    df_low = await client.get_security_bars(
        market_from_str(req.market),
        req.code,
        category_from_str(req.low_level),
        req.start,
        low_count,
    )

    # 分别分析
    high_analyser = ChanlunAnalyser(code=symbol, frequency=high_freq)
    low_analyser = ChanlunAnalyser(code=symbol, frequency=low_freq)
    high_result = high_analyser.process_klines(df_high)
    low_result = low_analyser.process_klines(df_low)

    # 多级别一致性分析
    mla = MultiLevelAnalyser()
    mla.add_level("high", high_analyser)
    mla.add_level("low", low_analyser)

    confluence = mla.compute_confluence_score("high", "low")

    # 最后一级笔的低级别走势
    low_qs: dict[str, Any] = {}
    if high_result.bis:
        last_bi = high_result.bis[-1]
        low_qs = mla.query_low_level_qs("high", "low", last_bi)

    # 格式化结果
    def fmt_result(result: Any) -> dict[str, Any]:
        d = result.to_dict()
        d["fractals"] = [
            {
                "fx_type": fx.fx_type.value,
                "date": result._fmt_dt(fx.k.date),
                "val": round(fx.val, 2),
                "index": fx.index,
            }
            for fx in result.fractals
        ]
        return d

    return _to_json_safe({
        "high_level": {
            "category": req.category,
            "result": fmt_result(high_result),
        },
        "low_level": {
            "category": req.low_level,
            "result": fmt_result(low_result),
        },
        "confluence": confluence,
        "low_level_qs": low_qs,
    })


class ChanlunRecommendRequest(ChanlunRequest):
    """缠论综合推荐请求。"""

    include_diagnosis: bool = Field(default=True, description="是否同时运行技术指标诊断")


@router.post("/chanlun/recommend")
async def chanlun_recommend(
    req: ChanlunRecommendRequest,
    client: Any = Depends(get_client),
) -> dict[str, Any]:
    """缠论综合推荐：结合 V4 买卖点质量评级 + 技术指标诊断，给出最终操作建议。

    输出包含：
    - 最高优先级买卖点（带质量评级）
    - 多级别一致性评分
    - 技术指标诊断摘要
    - 综合推荐动作（买入/持有/卖出）及理由
    """
    import numpy as np
    from easy_tdx.chanlun import ChanlunAnalyser
    from easy_tdx.chanlun.multi_level import MultiLevelAnalyser
    from easy_tdx.MyTT import MACD, MA, KDJ as MYTT_KDJ, RSI as MYTT_RSI

    symbol = f"{req.market}{req.code}"
    frequency_map: dict[str, str] = {
        "MIN_5": "5min", "MIN_15": "15min", "MIN_30": "30min",
        "MIN_60": "60min", "DAY": "daily", "WEEK": "weekly",
    }
    freq = frequency_map.get(req.category.upper(), "daily")

    # ── 1. 获取日线 K 线（缠论 + 诊断共用）──────────────────────────
    df = await client.get_security_bars(
        market_from_str(req.market), req.code, category_from_str("DAY"), 0, 500,
    )
    if df is None or len(df) < 100:
        return {"error": "数据不足", "symbol": symbol}

    closes = df["close"].tolist()
    volumes = df["vol"].tolist() if "vol" in df.columns else []
    highs = df["high"].tolist()
    lows = df["low"].tolist()
    latest_close = closes[-1]
    latest_date = str(df["date"].iloc[-1])[:10] if "date" in df.columns else ""

    # ── 2. 缠论 V4 分析 ──────────────────────────────────────────────
    analyser = ChanlunAnalyser(code=symbol, frequency="daily")
    chanlun_result = analyser.process_klines(df)
    mmds = chanlun_result.mmds

    # 取最高优先级买卖点（按质量评级排序）
    def _mmd_sort_key(m):
        q = getattr(m, "quality", None)
        grade_val = {"S": 5, "A": 4, "B": 3, "C": 2, "D": 1}.get(q.grade if q else None, 0)
        return (grade_val, m.confidence, m.bi.index if m.bi else 0)

    sorted_mmds = sorted(mmds, key=_mmd_sort_key, reverse=True)
    best_mmd = sorted_mmds[0] if sorted_mmds else None
    # 最新买卖点（按笔索引，用于 V79/V80 摘要）
    latest_mmd = max(mmds, key=lambda m: m.bi.index if m.bi else 0) if mmds else None

    # 买卖点摘要
    mmd_summary = []
    for m in sorted_mmds[:10]:
        q = getattr(m, "quality", None)
        mmd_summary.append({
            "type": m.mmd_type.value,
            "date": chanlun_result._fmt_dt(m.bi.end.k.date) if m.bi else None,
            "confidence": round(m.confidence, 2),
            "quality": {"grade": q.grade, "score": q.score, "reasons": q.reasons} if q else None,
            # V79 缠论增强条件
            "fractal_stability": getattr(m, "_fractal_stability_validation_v79", None),
            "distance_safety": getattr(m, "_mmd_distance_safety_v79", None),
            "multi_level_consistency": getattr(m, "_multi_level_structure_consistency_v79", None),
            "momentum_continuity": getattr(m, "_price_momentum_continuity_v79", None),
            # V80 缠论增强条件
            "zhongshu_distance": getattr(m, "_mmd_zhongshu_distance_v80", None),
            "volume_confirmation": getattr(m, "_volume_confirmation_v80", None),
            "ma_alignment": getattr(m, "_ma_alignment_strength_v80", None),
            "risk_reward": getattr(m, "_dynamic_risk_reward_v80", None),
        })

    # ── 3. 技术指标诊断（轻量版）─────────────────────────────────────
    diag: dict[str, Any] = {}
    if req.include_diagnosis and len(closes) >= 60:
        dif, dea, macd_hist = MACD(closes, 12, 26, 9)
        ma5 = MA(closes, 5)
        ma10 = MA(closes, 10)
        ma20 = MA(closes, 20)
        ma60 = MA(closes, 60)
        k, d, j = MYTT_KDJ(closes, highs, lows, 9, 3, 3)
        rsi14 = MYTT_RSI(closes, 14)

        latest_dif = dif[-1] if len(dif) > 0 else 0
        latest_dea = dea[-1] if len(dea) > 0 else 0
        golden_cross = (dif[-2] <= dea[-2] and latest_dif > latest_dea) if len(dif) > 1 else False
        dead_cross = (dif[-2] >= dea[-2] and latest_dif < latest_dea) if len(dif) > 1 else False

        # 均线排列
        ma_bull = all(v > 0 for v in (ma5[-1]-ma10[-1], ma10[-1]-ma20[-1], ma20[-1]-ma60[-1])) if all(x > 0 for x in [ma5[-1],ma10[-1],ma20[-1],ma60[-1]]) else False

        diag = {
            "macd": {
                "dif": round(latest_dif, 4), "dea": round(latest_dea, 4),
                "hist": round(macd_hist[-1], 4) if len(macd_hist) > 0 else 0,
                "golden_cross": golden_cross, "dead_cross": dead_cross,
                "above_zero": latest_dif > 0,
            },
            "kdj": {
                "k": round(k[-1], 2) if len(k) > 0 else 0, "d": round(d[-1], 2) if len(d) > 0 else 0,
                "j": round(j[-1], 2) if len(j) > 0 else 0,
                "overbought": (j[-1] if len(j) > 0 else 0) > 80, "oversold": (j[-1] if len(j) > 0 else 0) < 20,
            },
            "rsi": {
                "value": round(rsi14[-1], 2) if len(rsi14) > 0 else 50,
                "overbought": (rsi14[-1] if len(rsi14) > 0 else 50) > 70,
                "oversold": (rsi14[-1] if len(rsi14) > 0 else 50) < 30,
            },
            "ma_bullish_arrangement": ma_bull,
            "latest_close": round(latest_close, 2),
        }

    # ── 4. 综合推荐逻辑 ──────────────────────────────────────────────
    buy_signals = 0
    sell_signals = 0
    reasons_buy: list[str] = []
    reasons_sell: list[str] = []

    # 缠论信号打分
    if best_mmd:
        q = getattr(best_mmd, "quality", None)
        grade = q.grade if q else "C"
        conf = best_mmd.confidence
        mmd_type = best_mmd.mmd_type.value

        if "buy" in mmd_type:
            buy_signals += {"S": 3, "A": 2, "B": 1}.get(grade, 0)
            buy_signals += int(conf * 2)
            reasons_buy.append(f"缠论{mmd_type}({grade}级, 置信度{conf:.0%})")
        elif "sell" in mmd_type:
            sell_signals += {"S": 3, "A": 2, "B": 1}.get(grade, 0)
            sell_signals += int(conf * 2)
            reasons_sell.append(f"缠论{mmd_type}({grade}级, 置信度{conf:.0%})")

    # 诊断指标打分
    if diag:
        if diag.get("macd", {}).get("golden_cross"):
            buy_signals += 1
            reasons_buy.append("MACD 金叉")
        if diag.get("macd", {}).get("dead_cross"):
            sell_signals += 1
            reasons_sell.append("MACD 死叉")
        if diag.get("macd", {}).get("above_zero"):
            buy_signals += 0.5
        else:
            sell_signals += 0.5
        kdj = diag.get("kdj", {})
        if kdj.get("oversold"):
            buy_signals += 1
            reasons_buy.append("KDJ 超卖")
        elif kdj.get("overbought"):
            sell_signals += 1
            reasons_sell.append("KDJ 超买")
        rsi = diag.get("rsi", {})
        if rsi.get("oversold"):
            buy_signals += 0.5
            reasons_buy.append("RSI 超卖")
        elif rsi.get("overbought"):
            sell_signals += 0.5
            reasons_sell.append("RSI 超买")
        if diag.get("ma_bullish_arrangement"):
            buy_signals += 1
            reasons_buy.append("均线多头排列")
        else:
            sell_signals += 0.5

    net_score = buy_signals - sell_signals

    if net_score >= 4:
        action = "strong_buy"
        action_label = "强烈买入"
        action_color = "#22c55e"
    elif net_score >= 2:
        action = "buy"
        action_label = "买入"
        action_color = "#4ade80"
    elif net_score <= -4:
        action = "strong_sell"
        action_label = "强烈卖出"
        action_color = "#ef4444"
    elif net_score <= -2:
        action = "sell"
        action_label = "卖出"
        action_color = "#f87171"
    else:
        action = "hold"
        action_label = "持有观望"
        action_color = "#fbbf24"

    all_reasons = reasons_buy + reasons_sell
    reason_text = "；".join(all_reasons) if all_reasons else "无明显信号"

    return _to_json_safe({
        "symbol": symbol,
        "date": latest_date,
        "close": round(latest_close, 2),
        "action": action,
        "action_label": action_label,
        "action_color": action_color,
        "net_score": round(net_score, 1),
        "buy_signals": round(buy_signals, 1),
        "sell_signals": round(sell_signals, 1),
        "reason": reason_text,
        "best_mmd": {
            "type": best_mmd.mmd_type.value if best_mmd else None,
            "date": chanlun_result._fmt_dt(best_mmd.bi.end.k.date) if best_mmd and best_mmd.bi else None,
            "confidence": round(best_mmd.confidence, 2) if best_mmd else None,
            "quality": {
                "grade": getattr(getattr(best_mmd, "quality", None), "grade", None),
                "score": getattr(getattr(getattr(best_mmd, "quality", None), "score", None), "score", None),
            } if best_mmd else None,
        },
        "all_mmds": mmd_summary,
        "diagnosis": diag,
        # V79 缠论四维度量摘要（基于最新买卖点）
        "v79_summary": {
            "fractal_status": getattr(getattr(latest_mmd, "_fractal_stability_validation_v79", None), "fractal_status", None) if latest_mmd else None,
            "safety_level": getattr(getattr(latest_mmd, "_mmd_distance_safety_v79", None), "safety_level", None) if latest_mmd else None,
            "consistency_level": (getattr(getattr(latest_mmd, "_multi_level_structure_consistency_v79", None), "msg", "").split("consistent")[0] if latest_mmd and getattr(getattr(latest_mmd, "_multi_level_structure_consistency_v79", None), "msg", "") else None),
            "momentum_level": getattr(getattr(latest_mmd, "_price_momentum_continuity_v79", None), "momentum_level", None) if latest_mmd else None,
        } if latest_mmd else None,
        # V80 缠论四维度量摘要（条件252-255，基于最新买卖点）
        "v80_summary": {
            "zs_position": getattr(getattr(latest_mmd, "_mmd_zhongshu_distance_v80", None), "zs_position", None) if latest_mmd else None,
            "volume_confirmed": f"{'↑' if getattr(getattr(latest_mmd, '_volume_confirmation_v80', None), 'price_trend', None)=='up' else '↓'}{'↑' if getattr(getattr(latest_mmd, '_volume_confirmation_v80', None), 'volume_trend', None)=='up' else '↓'}" if latest_mmd and getattr(latest_mmd, "_volume_confirmation_v80", None) else None,
            "ma_alignment": getattr(getattr(latest_mmd, "_ma_alignment_strength_v80", None), "ma_alignment", None) if latest_mmd else None,
            "risk_level": getattr(getattr(latest_mmd, "_dynamic_risk_reward_v80", None), "risk_level", None) if latest_mmd else None,
        } if latest_mmd else None,
        # V81 缠论四维度量摘要（条件256-259，基于最新买卖点）
        "v81_summary": {
            "regime": getattr(getattr(latest_mmd, "_volatility_regime_transition_v81", None), "regime", None) if latest_mmd else None,
            "strength_level": getattr(getattr(latest_mmd, "_support_resistance_strength_v81", None), "strength_level", None) if latest_mmd else None,
            "energy_zone": getattr(getattr(latest_mmd, "_volume_price_energy_distribution_v81", None), "energy_zone", None) if latest_mmd else None,
            "window_quality": getattr(getattr(latest_mmd, "_signal_execution_window_v81", None), "window_quality", None) if latest_mmd else None,
        } if latest_mmd else None,
        # V82 缠论四维度量摘要（条件260-263，基于最新买卖点）
        "v82_summary": {
            "age_label": getattr(getattr(latest_mmd, "_mmd_age_decay_v82", None), "age_label", None) if latest_mmd else None,
            "retest_quality": getattr(getattr(latest_mmd, "_breakout_retest_confirm_v82", None), "retest_quality", None) if latest_mmd else None,
            "resonance": getattr(getattr(latest_mmd, "_macd_multi_tf_resonance_v82", None), "resonance", None) if latest_mmd else None,
            "compression_level": getattr(getattr(latest_mmd, "_volatility_compression_breakout_v82", None), "compression_level", None) if latest_mmd else None,
        } if latest_mmd else None,
    })


@router.post("/chanlun/train/session")
async def chanlun_train_session(
    req: ChanlunRequest,
    client: Any = Depends(get_client),
) -> dict[str, Any]:
    """创建缠论学习训练会话（P0：逐步揭示训练 + 逐笔复盘讲解）。

    返回：
    - bars：K 线数据（与 /bars 相同格式）
    - bis/xds/zss/mmds/fractals/bcs/boll：完整缠论结构
    - candidates：训练候选点（关键分型 + 买卖点信号），供前端逐步揭示时暂停提问
      [{index, date, kind: fractal|mmd, fx_type, signal: null | {type, confidence, grade}}]
    - mmd_outcomes：每个买卖点的信号后 5/10/20 日收益（复盘验证准确率用）
    """
    from easy_tdx.chanlun import ChanlunAnalyser

    # 1. 取行情
    df = await client.get_security_bars(
        market_from_str(req.market),
        req.code,
        category_from_str(req.category),
        req.start,
        req.count,
    )
    if df is None or len(df) == 0:
        return {"error": "未取到行情数据", "bars": [], "candidates": [], "mmd_outcomes": []}

    symbol = f"{req.market}{req.code}"
    frequency_map: dict[str, str] = {
        "MIN_1": "1min", "MIN_5": "5min", "MIN_15": "15min",
        "MIN_30": "30min", "MIN_60": "60min", "DAY": "daily",
        "WEEK": "weekly", "MONTH": "monthly", "YEAR": "yearly",
    }
    freq = frequency_map.get(req.category.upper(), req.category)
    analyser = ChanlunAnalyser(code=symbol, frequency=freq)
    result = analyser.process_klines(df)

    # 2. 组装训练会话负载（纯函数，可单测）
    payload = build_train_session_payload(result, df, req.category)
    payload["code"] = symbol
    payload["frequency"] = freq
    return payload
