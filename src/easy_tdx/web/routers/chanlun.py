"""缠论分析路由。"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, cast

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field

from easy_tdx.web.deps import get_client, get_mac_client_optional
from easy_tdx.web.klines import fetch_paged_bars, fetch_qfq_klines  # 共享 K 线取数（MAC 回退）
from easy_tdx.web.schemas import ChanlunRequest

logger = logging.getLogger(__name__)

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


def _build_signal_explanation(mmd: Any) -> str:
    """V422 错误归因「正确解读」（D4：复用 mmd.msg + V102 建议拼接）。

    从买卖点对象生成一段可读解读：信号类型 + 置信度 + V102 操作建议。
    """
    parts: list[str] = []
    parts.append(f"模型识别为 {mmd.mmd_type.value}（置信度 {mmd.confidence:.0%}）")
    _decision = getattr(mmd, "_decision_support", None) or {}
    advice = _decision.get("action_recommendation")
    if advice:
        parts.append(f"V102 建议：{advice}")
    msg = getattr(mmd, "msg", "")
    if msg:
        parts.append(str(msg))
    return "；".join(parts)


def _filter_candidates_by_difficulty(
    candidates: list[dict[str, Any]], difficulty: str, seed: int = 0
) -> list[dict[str, Any]]:
    """按难度过滤训练候选点（D3：难度 = f(信号置信度, 是否干扰项)）。

    - easy：仅高置信度买卖点（confidence >= 0.8）+ 少量干扰项
    - medium：全部候选点（现状，不过滤）
    - hard：低置信度买卖点（confidence < 0.75）+ 更多干扰项

    用 seed 初始化 random 做干扰项采样，保证同 (code, difficulty, seed) 出题可复现。
    """
    import random

    if difficulty not in ("easy", "medium", "hard"):
        difficulty = "medium"
    mmd_cands = [c for c in candidates if c.get("kind") == "mmd"]
    fx_cands = [c for c in candidates if c.get("kind") == "fractal"]

    if difficulty == "medium":
        return candidates

    if difficulty == "easy":
        picked_mmd = [c for c in mmd_cands if (c.get("signal") or {}).get("confidence", 0) >= 0.8]
        # 少量干扰项：mmd 数量的 1/3，seed 复现
        rng = random.Random(seed)
        n_fx = max(len(picked_mmd) // 3, 0)
        picked_fx = rng.sample(fx_cands, min(n_fx, len(fx_cands))) if fx_cands and n_fx > 0 else []
    else:  # hard
        picked_mmd = [c for c in mmd_cands if (c.get("signal") or {}).get("confidence", 0) < 0.75]
        # 更多干扰项：mmd 数量的 1/2
        rng = random.Random(seed)
        n_fx = max(len(picked_mmd) // 2, 0)
        picked_fx = rng.sample(fx_cands, min(n_fx, len(fx_cands))) if fx_cands and n_fx > 0 else []

    return sorted(picked_mmd + picked_fx, key=lambda c: c["index"])


def build_train_session_payload(
    result: Any, df: pd.DataFrame, category: str, difficulty: str = "medium", seed: int = 0
) -> dict[str, Any]:
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
        bars.append(
            {
                "datetime": str(dt)[:19].replace(" ", "T"),
                "open": round(float(row["open"]), 3),
                "close": round(float(row["close"]), 3),
                "high": round(float(row["high"]), 3),
                "low": round(float(row["low"]), 3),
                "vol": float(row.get("vol", 0) or 0),
                "amount": float(row.get("amount", 0) or 0),
            }
        )

    # 结构数据（复用 analyze 的序列化）
    d = result.to_dict()
    d["fractals"] = [
        {
            "fx_type": fx.fx_type.value,
            "date": result._fmt_dt(result._fx_anchor_datetime(fx)),
            "val": round(fx.val, 2),
            "index": fx.index,
            "bar_index": fx.bar_index,
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
        k_idx = mmd.bi.end.bar_index
        # V344: 训练教学展示 V102 决策支持（仅 3买/3卖 有建议）
        _v102_scorecard = getattr(mmd, "_signal_quality_scorecard", None) or {}
        _v102_decision = getattr(mmd, "_decision_support", None) or {}
        mmd_cands.append(
            {
                "index": k_idx,
                "date": result._fmt_dt(result._fx_anchor_datetime(mmd.bi.end)),
                "kind": "mmd",
                "fx_type": None,
                "signal": {
                    "type": mmd.mmd_type.value,
                    "confidence": round(mmd.confidence, 2),
                    "grade": getattr(getattr(mmd, "quality", None), "grade", None),
                    "v102_grade": _v102_scorecard.get("overall_grade") or None,
                    "v102_advice": _v102_decision.get("action_recommendation") or None,
                    # V422: 错误归因「正确解读」（D4：复用 mmd.msg + V102 建议）
                    "explanation": _build_signal_explanation(mmd),
                },
            }
        )
    mmd_idx_set = {c["index"] for c in mmd_cands}
    fx_cands: list[dict[str, Any]] = []
    for fx in result.fractals:
        k_idx = fx.bar_index
        if any(abs(k_idx - m) <= 3 for m in mmd_idx_set):
            continue
        fx_cands.append(
            {
                "index": k_idx,
                "date": result._fmt_dt(result._fx_anchor_datetime(fx)),
                "kind": "fractal",
                "fx_type": fx.fx_type.value,
                "signal": None,
            }
        )
    # 均匀采样干扰项：总数（信号+干扰）控制在 ~40
    target_total = 40
    distract_max = max(target_total - len(mmd_cands), 0)
    if len(fx_cands) > distract_max:
        step = len(fx_cands) / distract_max
        fx_cands = [fx_cands[int(i * step)] for i in range(distract_max)]
    candidates = sorted(mmd_cands + fx_cands, key=lambda c: c["index"])
    # V421: 难度分级过滤（D3），seed 保证出题可复现
    candidates = _filter_candidates_by_difficulty(candidates, difficulty, seed)

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
        return round((float(closes[end]) / float(base) - 1) * 100, 2)

    mmd_outcomes: list[dict[str, Any]] = []
    for mmd in result.mmds:
        if not mmd.bi:
            continue
        k_idx = mmd.bi.end.k.k_index
        outcomes: dict[str, Any] = {
            "type": mmd.mmd_type.value,
            "date": result._fmt_dt(mmd.bi.end.k.date),
            "price": round(result.klines[k_idx].close, 2)
            if 0 <= k_idx < len(result.klines)
            else None,
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

    return cast(
        dict[str, Any],
        _to_json_safe(
            {
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
            }
        ),
    )


@router.post("/chanlun/analyze")
async def chanlun_analyze(
    req: ChanlunRequest,
    client: Any = Depends(get_client),
    mac_client: Any | None = Depends(get_mac_client_optional),
) -> dict[str, Any]:
    """执行缠论分析。

    自动从 TDX 服务器获取 K 线数据，运行完整缠论计算管道，
    返回笔、中枢、线段、买卖点、背驰、分型等分析结果。
    """
    from easy_tdx.chanlun import ChanlunAnalyser, ChanlunConfig

    # 1. Fetch kline data（QFQ 前复权，与前端 /bars 同一价格体系）
    df = await _fetch_request_klines(
        mac_client,
        client,
        req.market,
        req.code,
        req.category,
        req.start,
        req.count,
    )

    # V599: 按可选日期范围截断，让缠论分析与前端 K 线图窗口精确对齐
    # （回测页用 start_date/end_date 截取 K 线，这里用同一范围分析）。
    if req.start_date or req.end_date:
        col = "date" if "date" in df.columns else "datetime"
        ts = pd.to_datetime(df[col]).dt.normalize()
        mask = pd.Series(True, index=df.index)
        if req.start_date:
            mask &= ts >= pd.Timestamp(req.start_date)
        if req.end_date:
            mask &= ts <= pd.Timestamp(req.end_date)
        df = df[mask].reset_index(drop=True)

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
    # V708: 多级别递归深度经前端指定（1=线段级别；标准请求不传时回落 1）。
    analyser = ChanlunAnalyser(
        code=symbol,
        frequency=freq,
        config=ChanlunConfig(recursion_depth=req.recursion_depth),
    )
    result = analyser.process_klines(df)

    # 3. 返回完整分析结果，包括分型数据和BOLL
    d = result.to_dict()

    # 添加分型数据
    d["fractals"] = [
        {
            "fx_type": fx.fx_type.value,
            "date": result._fmt_dt(result._fx_anchor_datetime(fx)),
            "val": round(fx.val, 2),
            "index": fx.index,
            "bar_index": fx.bar_index,
        }
        for fx in result.fractals
    ]

    # 添加BOLL数据
    if result.boll:
        _ = len(result.boll.upper)
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

    # 4. 买卖点分类准确度验证（前瞻命中率 vs 随机基准）——让用户核对
    #    「哪类缠论买卖点信号真的准」，直接服务择时交易的可信度判断。
    try:
        from easy_tdx.backtest.signal_accuracy import compute_signal_accuracy_by_type

        closes = [float(k.close) for k in result.klines]
        mmd_signals = [
            {
                "type": mmd.mmd_type.value,
                "bar_index": mmd.bi.end.bar_index if mmd.bi else None,
            }
            for mmd in result.mmds
        ]
        d["signal_accuracy"] = compute_signal_accuracy_by_type(closes, mmd_signals)
    except Exception:
        # 准确度验证是附加信息，失败不应阻断主分析结果
        d["signal_accuracy"] = None

    # V534: 基本面估值（PE/PB），复用诊断页的离线取数 helper（无缓存时为 None）
    try:
        from easy_tdx.web.routers.diagnosis import _fetch_diagnosis_valuation

        latest_close = float(result.klines[-1].close) if result.klines else 0.0
        d["valuation"] = _fetch_diagnosis_valuation(req.market, req.code, latest_close)
    except Exception:  # noqa: BLE001 — 估值失败不阻断缠论分析
        d["valuation"] = None

    return d


class ChanlunMultiLevelRequest(ChanlunRequest):
    """多级别缠论分析请求。"""

    low_level: str = Field(default="MIN_30", description="低级别周期（如 MIN_30, MIN_5）")


@router.post("/chanlun/multi-level")
async def chanlun_multi_level(
    req: ChanlunMultiLevelRequest,
    client: Any = Depends(get_client),
    mac_client: Any | None = Depends(get_mac_client_optional),
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
    # V720: category/low_level 不在白名单时显式 400（此前静默回落 daily/30min，
    # 与 analyze 同参 400 的行为不一致，且把错别字悄悄当成日线分析）。
    if req.category.upper() not in frequency_map:
        raise HTTPException(
            status_code=400,
            detail=f"非法周期 '{req.category}'，可选值: {', '.join(frequency_map)}",
        )
    low_raw = req.low_level or "MIN_30"  # 空低级别 = 默认 30min（保留原语义）
    if low_raw.upper() not in frequency_map:
        raise HTTPException(
            status_code=400,
            detail=f"非法低级别周期 '{req.low_level}'，可选值: {', '.join(frequency_map)}",
        )
    high_freq = frequency_map[req.category.upper()]
    low_freq = frequency_map[low_raw.upper()]

    symbol = f"{req.market}{req.code}"

    # 获取高级别数据（QFQ 前复权）
    df_high = await fetch_qfq_klines(
        mac_client,
        client,
        req.market,
        req.code,
        req.category,
        req.start,
        req.count,
    )
    # 获取低级别数据（需要覆盖高级别的时间范围，否则最新高级别笔的低级别走势为空）
    # 每自然日对应的低级别 K 线数（A股一天约4小时交易时段）
    _bars_per_day = {
        "MIN_1": 240,
        "MIN_5": 48,
        "MIN_15": 16,
        "MIN_30": 8,
        "MIN_60": 4,
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
    df_low = await fetch_qfq_klines(
        mac_client,
        client,
        req.market,
        req.code,
        req.low_level,
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
        d: dict[str, Any] = result.to_dict()
        d["fractals"] = [
            {
                "fx_type": fx.fx_type.value,
                "date": result._fmt_dt(result._fx_anchor_datetime(fx)),
                "val": round(fx.val, 2),
                "index": fx.index,
                "bar_index": fx.bar_index,
            }
            for fx in result.fractals
        ]
        return d

    # V541: 高级别（日线）补基本面估值，与单级别 chanlun_analyze 对齐
    high_valuation: dict[str, Any] | None = None
    try:
        from easy_tdx.web.routers.diagnosis import _fetch_diagnosis_valuation

        latest_close = float(high_result.klines[-1].close) if high_result.klines else 0.0
        high_valuation = _fetch_diagnosis_valuation(req.market, req.code, latest_close)
    except Exception:  # noqa: BLE001
        high_valuation = None

    return cast(
        dict[str, Any],
        _to_json_safe(
            {
                "high_level": {
                    "category": req.category,
                    "result": {**fmt_result(high_result), "valuation": high_valuation},
                },
                "low_level": {
                    "category": req.low_level,
                    "result": fmt_result(low_result),
                },
                "confluence": confluence,
                "low_level_qs": low_qs,
            }
        ),
    )


class ChanlunRecommendRequest(ChanlunRequest):
    """缠论综合推荐请求。"""

    include_diagnosis: bool = Field(default=True, description="是否同时运行技术指标诊断")


@router.post("/chanlun/recommend")
async def chanlun_recommend(
    req: ChanlunRecommendRequest,
    client: Any = Depends(get_client),
    mac_client: Any | None = Depends(get_mac_client_optional),
) -> dict[str, Any]:
    """缠论综合推荐：结合 V4 买卖点质量评级 + 技术指标诊断，给出最终操作建议。

    输出包含：
    - 最高优先级买卖点（带质量评级）
    - 多级别一致性评分
    - 技术指标诊断摘要
    - 综合推荐动作（买入/持有/卖出）及理由
    """
    from easy_tdx.chanlun import ChanlunAnalyser, ChanlunConfig
    from easy_tdx.MyTT import KDJ as MYTT_KDJ
    from easy_tdx.MyTT import MA, MACD
    from easy_tdx.MyTT import RSI as MYTT_RSI

    symbol = f"{req.market}{req.code}"
    frequency_map: dict[str, str] = {
        "MIN_5": "5min",
        "MIN_15": "15min",
        "MIN_30": "30min",
        "MIN_60": "60min",
        "DAY": "daily",
        "WEEK": "weekly",
    }
    _ = frequency_map.get(req.category.upper(), "daily")

    # ── 1. 获取日线 K 线（缠论 + 诊断共用，QFQ 前复权）────────────
    df = await fetch_qfq_klines(mac_client, client, req.market, req.code, "DAY", 0, 500)
    if df is None or len(df) < 100:
        return {"error": "数据不足", "symbol": symbol}

    closes = df["close"].tolist()
    _ = df["vol"].tolist() if "vol" in df.columns else []
    highs = df["high"].tolist()
    lows = df["low"].tolist()
    latest_close = closes[-1]
    latest_date = str(df["date"].iloc[-1])[:10] if "date" in df.columns else ""

    # ── 2. 缠论 V4 分析 ──────────────────────────────────────────────
    analyser = ChanlunAnalyser(
        code=symbol, frequency="daily", config=ChanlunConfig(recursion_depth=req.recursion_depth)
    )
    chanlun_result = analyser.process_klines(df)
    mmds = chanlun_result.mmds

    # 取最高优先级买卖点（按质量评级排序）
    def _mmd_sort_key(m: Any) -> tuple[int, float, int]:
        q = getattr(m, "quality", None)
        grade = str(getattr(q, "grade", "")) if q else ""
        grade_val = {"S": 5, "A": 4, "B": 3, "C": 2, "D": 1}.get(grade, 0)
        return (grade_val, m.confidence, m.bi.index if m.bi else 0)

    sorted_mmds = sorted(mmds, key=_mmd_sort_key, reverse=True)
    best_mmd = sorted_mmds[0] if sorted_mmds else None
    # 最新买卖点（按笔索引，用于 V79/V80 摘要）
    latest_mmd = max(mmds, key=lambda m: m.bi.index if m.bi else 0) if mmds else None

    # 买卖点摘要
    mmd_summary = []
    for m in sorted_mmds[:10]:
        q = getattr(m, "quality", None)
        mmd_summary.append(
            {
                "type": m.mmd_type.value,
                "date": chanlun_result._fmt_dt(m.bi.end.k.date) if m.bi else None,
                "confidence": round(m.confidence, 2),
                "quality": {"grade": q.grade, "score": q.score, "reasons": q.reasons}
                if q
                else None,
                # V79 缠论增强条件
                "fractal_stability": getattr(m, "_fractal_stability_validation_v79", None),
                "distance_safety": getattr(m, "_mmd_distance_safety_v79", None),
                "multi_level_consistency": getattr(
                    m, "_multi_level_structure_consistency_v79", None
                ),
                "momentum_continuity": getattr(m, "_price_momentum_continuity_v79", None),
                # V80 缠论增强条件
                "zhongshu_distance": getattr(m, "_mmd_zhongshu_distance_v80", None),
                "volume_confirmation": getattr(m, "_volume_confirmation_v80", None),
                "ma_alignment": getattr(m, "_ma_alignment_strength_v80", None),
                "risk_reward": getattr(m, "_dynamic_risk_reward_v80", None),
            }
        )

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
        ma_bull = (
            all(v > 0 for v in (ma5[-1] - ma10[-1], ma10[-1] - ma20[-1], ma20[-1] - ma60[-1]))
            if all(x > 0 for x in [ma5[-1], ma10[-1], ma20[-1], ma60[-1]])
            else False
        )

        diag = {
            "macd": {
                "dif": round(latest_dif, 4),
                "dea": round(latest_dea, 4),
                "hist": round(macd_hist[-1], 4) if len(macd_hist) > 0 else 0,
                "golden_cross": golden_cross,
                "dead_cross": dead_cross,
                "above_zero": latest_dif > 0,
            },
            "kdj": {
                "k": round(k[-1], 2) if len(k) > 0 else 0,
                "d": round(d[-1], 2) if len(d) > 0 else 0,
                "j": round(j[-1], 2) if len(j) > 0 else 0,
                "overbought": (j[-1] if len(j) > 0 else 0) > 80,
                "oversold": (j[-1] if len(j) > 0 else 0) < 20,
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
    buy_signals: float = 0.0
    sell_signals: float = 0.0
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

    # V79 一致性摘要（运行时挂载字段，类型不明，先归一为 str）
    _v79_mlsc = (
        getattr(latest_mmd, "_multi_level_structure_consistency_v79", None) if latest_mmd else None
    )
    _v79_mlsc_msg = str(getattr(_v79_mlsc, "msg", "")) if _v79_mlsc else ""
    _v79_consistency = _v79_mlsc_msg.split("consistent")[0] if _v79_mlsc_msg else None

    return cast(
        dict[str, Any],
        _to_json_safe(
            {
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
                    "date": chanlun_result._fmt_dt(best_mmd.bi.end.k.date)
                    if best_mmd and best_mmd.bi
                    else None,
                    "confidence": round(best_mmd.confidence, 2) if best_mmd else None,
                    "quality": {
                        "grade": getattr(getattr(best_mmd, "quality", None), "grade", None),
                        "score": getattr(
                            getattr(getattr(best_mmd, "quality", None), "score", None),
                            "score",
                            None,
                        ),
                    }
                    if best_mmd
                    else None,
                },
                "all_mmds": mmd_summary,
                "diagnosis": diag,
                # V79 缠论四维度量摘要（基于最新买卖点）
                "v79_summary": {
                    "fractal_status": getattr(
                        getattr(latest_mmd, "_fractal_stability_validation_v79", None),
                        "fractal_status",
                        None,
                    )
                    if latest_mmd
                    else None,
                    "safety_level": getattr(
                        getattr(latest_mmd, "_mmd_distance_safety_v79", None), "safety_level", None
                    )
                    if latest_mmd
                    else None,
                    "consistency_level": _v79_consistency,
                    "momentum_level": getattr(
                        getattr(latest_mmd, "_price_momentum_continuity_v79", None),
                        "momentum_level",
                        None,
                    )
                    if latest_mmd
                    else None,
                }
                if latest_mmd
                else None,
                # V80 缠论四维度量摘要（条件252-255，基于最新买卖点）
                "v80_summary": {
                    "zs_position": getattr(
                        getattr(latest_mmd, "_mmd_zhongshu_distance_v80", None), "zs_position", None
                    )
                    if latest_mmd
                    else None,
                    "volume_confirmed": f"{'↑' if getattr(getattr(latest_mmd, '_volume_confirmation_v80', None), 'price_trend', None) == 'up' else '↓'}{'↑' if getattr(getattr(latest_mmd, '_volume_confirmation_v80', None), 'volume_trend', None) == 'up' else '↓'}"
                    if latest_mmd and getattr(latest_mmd, "_volume_confirmation_v80", None)
                    else None,
                    "ma_alignment": getattr(
                        getattr(latest_mmd, "_ma_alignment_strength_v80", None),
                        "ma_alignment",
                        None,
                    )
                    if latest_mmd
                    else None,
                    "risk_level": getattr(
                        getattr(latest_mmd, "_dynamic_risk_reward_v80", None), "risk_level", None
                    )
                    if latest_mmd
                    else None,
                }
                if latest_mmd
                else None,
                # V81 缠论四维度量摘要（条件256-259，基于最新买卖点）
                "v81_summary": {
                    "regime": getattr(
                        getattr(latest_mmd, "_volatility_regime_transition_v81", None),
                        "regime",
                        None,
                    )
                    if latest_mmd
                    else None,
                    "strength_level": getattr(
                        getattr(latest_mmd, "_support_resistance_strength_v81", None),
                        "strength_level",
                        None,
                    )
                    if latest_mmd
                    else None,
                    "energy_zone": getattr(
                        getattr(latest_mmd, "_volume_price_energy_distribution_v81", None),
                        "energy_zone",
                        None,
                    )
                    if latest_mmd
                    else None,
                    "window_quality": getattr(
                        getattr(latest_mmd, "_signal_execution_window_v81", None),
                        "window_quality",
                        None,
                    )
                    if latest_mmd
                    else None,
                }
                if latest_mmd
                else None,
                # V82 缠论四维度量摘要（条件260-263，基于最新买卖点）
                "v82_summary": {
                    "age_label": getattr(
                        getattr(latest_mmd, "_mmd_age_decay_v82", None), "age_label", None
                    )
                    if latest_mmd
                    else None,
                    "retest_quality": getattr(
                        getattr(latest_mmd, "_breakout_retest_confirm_v82", None),
                        "retest_quality",
                        None,
                    )
                    if latest_mmd
                    else None,
                    "resonance": getattr(
                        getattr(latest_mmd, "_macd_multi_tf_resonance_v82", None), "resonance", None
                    )
                    if latest_mmd
                    else None,
                    "compression_level": getattr(
                        getattr(latest_mmd, "_volatility_compression_breakout_v82", None),
                        "compression_level",
                        None,
                    )
                    if latest_mmd
                    else None,
                }
                if latest_mmd
                else None,
            }
        ),
    )


def _fetch_request_klines(
    mac_client: Any,
    client: Any,
    market: str,
    code: str,
    category: str,
    start: int,
    count: int,
) -> Any:
    """V722: 按请求取 K 线；count>800 分流到 fetch_paged_bars 循环翻页。

    QFQ 口径与列规整同 fetch_qfq_klines；start>0 时不分页（历史偏移语义
    只在单页内有效，分页路径固定从最新 bar 往回凑 lookback）。
    """
    if count > 800 and start == 0:
        return fetch_paged_bars(mac_client, client, market, code, category, lookback=count)
    return fetch_qfq_klines(mac_client, client, market, code, category, start, count)


@router.post("/chanlun/train/session")
async def chanlun_train_session(
    req: ChanlunRequest,
    client: Any = Depends(get_client),
    mac_client: Any | None = Depends(get_mac_client_optional),
    difficulty: str = "medium",
    seed: int = 0,
) -> dict[str, Any]:
    """创建缠论学习训练会话（P0：逐步揭示训练 + 逐笔复盘讲解）。

    返回：
    - bars：K 线数据（与 /bars 相同格式）
    - bis/xds/zss/mmds/fractals/bcs/boll：完整缠论结构
    - candidates：训练候选点（关键分型 + 买卖点信号），供前端逐步揭示时暂停提问
      [{index, date, kind: fractal|mmd, fx_type, signal: null | {type, confidence, grade}}]
    - mmd_outcomes：每个买卖点的信号后 5/10/20 日收益（复盘验证准确率用）
    """
    from easy_tdx.chanlun import ChanlunAnalyser, ChanlunConfig

    # 1. 取行情（QFQ 前复权，与 /bars 同一价格体系）
    # V722: count>800 时走服务端循环翻页（start 仅单页协议内有效）
    df = await _fetch_request_klines(
        mac_client, client, req.market, req.code, req.category, req.start, req.count
    )
    if df is None or len(df) == 0:
        return {"error": "未取到行情数据", "bars": [], "candidates": [], "mmd_outcomes": []}

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
    analyser = ChanlunAnalyser(
        code=symbol, frequency=freq, config=ChanlunConfig(recursion_depth=req.recursion_depth)
    )
    result = analyser.process_klines(df)

    # 2. 组装训练会话负载（纯函数，可单测；V421 难度分级 + seed 复现）
    payload = build_train_session_payload(result, df, req.category, difficulty, seed)
    payload["code"] = symbol
    payload["frequency"] = freq
    return payload


@router.post("/chanlun/train/score")
async def chanlun_train_score(req: dict[str, Any]) -> dict[str, Any]:
    """提交一轮「逐步揭示训练」的成绩（V90：持久化 + 排行榜）。

    请求体：
    {
      "player_name": "学员甲",
      "score": 18,
      "total_asked": 8, "hit_count": 6, "hit_rate": 75.0,
      "code": "600519", "market": "SH", "category": "DAY", "count": 400,
      "extra": {"best_streak": 3}   // 可选
    }
    """
    from easy_tdx.web.train_store import TrainScore, get_score_store

    # V720: 数值字段前置校验（此前 score="abc" 等在 int()/float() 处抛
    # ValueError → 500；松散 dict 端点形状非法一律 400）。
    def _num_field(name: str, default: float) -> float:
        raw = req.get(name, default)
        if raw is None or raw == "":
            return default
        try:
            return float(raw)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail=f"{name} 必须是数字") from None

    _num_field("score", 0)
    _num_field("hit_rate", 0)
    for _name in ("count", "total_asked", "hit_count"):
        raw = req.get(_name)
        if raw is None or raw == "":
            continue
        try:
            int(raw)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail=f"{_name} 必须是整数") from None
        # 浮点整型检查：count=3.5 之类也应拒绝（int() 会静默截断 float，但 str "3.5" 抛错）
        if isinstance(raw, float) and not raw.is_integer():
            raise HTTPException(status_code=400, detail=f"{_name} 必须是整数")

    def _run() -> dict[str, Any]:
        store = get_score_store()
        rec = TrainScore(
            score=float(req.get("score", 0) or 0),
            player_name=str(req.get("player_name") or "学员").strip() or "学员",
            code=str(req.get("code") or "").strip(),
            market=str(req.get("market") or "SZ").upper()[:2],
            category=str(req.get("category") or "DAY").upper(),
            difficulty=str(req.get("difficulty") or "medium").lower(),
            count=int(req.get("count", 400) or 400),
            total_asked=int(req.get("total_asked", 0) or 0),
            hit_count=int(req.get("hit_count", 0) or 0),
            hit_rate=float(req.get("hit_rate", 0) or 0),
            extra=dict(req.get("extra") or {}),
        )
        store.add(rec)
        return {"ok": True, "id": rec.id, "score": rec.to_dict()}

    try:
        return await asyncio.to_thread(_run)
    except Exception as e:  # noqa: BLE001
        logger.exception("chanlun train score 失败")
        raise HTTPException(status_code=500, detail=f"提交成绩失败: {e}") from e


@router.get("/chanlun/train/leaderboard")
async def chanlun_train_leaderboard(
    limit: int = 20,
    category: str | None = None,
    difficulty: str | None = None,
) -> dict[str, Any]:
    """V90 训练排行榜：得分降序、命中率降序，可限定周期/难度。

    Query:
      limit=20   返回条数（默认 20）
      category=DAY  只返回该周期（缺省全部）
      difficulty=hard  只返回该难度（缺省全部）
    """
    from easy_tdx.web.train_store import get_score_store

    def _run() -> dict[str, Any]:
        store = get_score_store()
        rows = store.leaderboard(limit=limit, category=category, difficulty=difficulty)
        summary = store.summary(category=category, difficulty=difficulty)
        return {
            "items": [r.to_dict() for r in rows],
            "count": len(rows),
            "summary": summary,
        }

    try:
        return await asyncio.to_thread(_run)
    except Exception as e:  # noqa: BLE001
        logger.exception("chanlun train leaderboard 失败")
        raise HTTPException(status_code=500, detail=f"排行榜失败: {e}") from e


@router.get("/learn/progress")
async def learn_progress(player: str = "学员") -> dict[str, Any]:
    """V424: 学习进度聚合——按 category×difficulty 统计命中率/题数。"""
    from easy_tdx.web.train_store import get_score_store

    def _run() -> dict[str, Any]:
        store = get_score_store()
        data = store.progress(player)
        return {"player": player, "matrix": data["matrix"], "recent": data["recent"]}

    try:
        return await asyncio.to_thread(_run)
    except Exception as e:  # noqa: BLE001
        logger.exception("learn progress 失败")
        raise HTTPException(status_code=500, detail=f"学习进度失败: {e}") from e


@router.post("/learn/mistakes")
async def learn_mistakes_add(req: dict[str, Any]) -> dict[str, Any]:
    """V426: 记录一道错题（供复习）。"""
    from easy_tdx.web.train_store import get_score_store

    # V720: 错题字段形状校验——question_date/signal_type/user_choice/actual/
    # explanation 会原样入库 SQLite，传数组/对象会导致存储层类型混乱，
    # 这里限制为标量（str/int/float/None），非法 400。
    _SCALAR_OK = (str, int, float, type(None))
    for _name in (
        "player",
        "symbol",
        "category",
        "difficulty",
        "question_date",
        "signal_type",
        "user_choice",
        "actual",
        "explanation",
    ):
        if _name in req and not isinstance(req[_name], _SCALAR_OK):
            raise HTTPException(status_code=400, detail=f"{_name} 必须是标量（字符串/数字）")

    def _run() -> dict[str, Any]:
        get_score_store().add_mistake(req)
        return {"ok": True}

    try:
        return await asyncio.to_thread(_run)
    except Exception as e:  # noqa: BLE001
        logger.exception("learn mistakes add 失败")
        raise HTTPException(status_code=500, detail=f"记录错题失败: {e}") from e


@router.get("/learn/mistakes")
async def learn_mistakes_list(
    player: str = "学员",
    category: str | None = None,
) -> dict[str, Any]:
    """V426: 错题复习列表（按时间倒序，可限定玩家/周期）。"""
    from easy_tdx.web.train_store import get_score_store

    def _run() -> dict[str, Any]:
        rows = get_score_store().list_mistakes(player=player, category=category)
        return {"items": rows, "count": len(rows)}

    try:
        return await asyncio.to_thread(_run)
    except Exception as e:  # noqa: BLE001
        logger.exception("learn mistakes list 失败")
        raise HTTPException(status_code=500, detail=f"错题列表失败: {e}") from e
