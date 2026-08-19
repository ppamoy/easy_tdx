"""股票诊断API路由。

提供单只股票的全面技术分析，帮助投资者做出买卖决策。

功能：
1. 缠论结构分析（笔/中枢/买卖点）
2. BOLL位置分析
3. MACD状态分析
4. 成交量分析
5. 综合评分和操作建议
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends

from easy_tdx.web.convert import category_from_str, market_from_str
from easy_tdx.web.deps import get_client
from easy_tdx.web.schemas import StockIdentifier

router = APIRouter(tags=["diagnosis"])
logger = logging.getLogger(__name__)


@router.post("/diagnosis/analyze")
async def diagnose_stock(
    req: StockIdentifier,
    client: Any = Depends(get_client),
) -> dict[str, Any]:
    """分析单只股票的技术面，给出买卖建议。

    请求参数：
    - market: 市场 (SZ/SH)
    - code: 6位股票代码
    """
    from easy_tdx.chanlun import ChanlunAnalyser, ChanlunConfig
    from easy_tdx.MyTT import MACD, MA, BOLL

    market = req.market
    code = req.code
    symbol = f"{market}{code}"

    # 获取日线数据
    df = await client.get_security_bars(
        market_from_str(market),
        code,
        category_from_str("DAY"),
        0,
        500,
    )

    if df is None or len(df) < 100:
        return {
            "error": "数据不足，无法进行分析",
            "symbol": symbol,
        }

    closes = df["close"].tolist()
    volumes = df["vol"].tolist()
    highs = df["high"].tolist()
    lows = df["low"].tolist()
    opens = df["open"].tolist()
    dates = [str(d)[:10] for d in df["datetime"].tolist()] if "datetime" in df.columns else []
    latest_close = closes[-1]
    latest_date = dates[-1] if dates else ""

    # ── 缠论分析 ──────────────────────────────────────────────────────
    analyser = ChanlunAnalyser(code=symbol, frequency="daily")
    result = analyser.process_klines(df)

    # ── MACD分析 ──────────────────────────────────────────────────────
    dif, dea, macd_hist = MACD(closes, fast=12, slow=26, signal=9)
    latest_dif = dif[-1] if len(dif) > 0 else 0
    latest_dea = dea[-1] if len(dea) > 0 else 0
    latest_macd = macd_hist[-1] if len(macd_hist) > 0 else 0

    # MACD状态
    macd_golden = False  # DIF上穿DEA
    macd_dead = False    # DIF下穿DEA
    if len(dif) >= 2 and len(dea) >= 2:
        macd_golden = dif[-2] <= dea[-2] and dif[-1] > dea[-1]
        macd_dead = dif[-2] >= dea[-2] and dif[-1] < dea[-1]

    macd_above_zero = latest_dif > 0 and latest_dea > 0
    macd_trending_up = latest_macd > 0 and (len(macd_hist) >= 2 and macd_hist[-1] > macd_hist[-2])
    macd_trending_down = latest_macd < 0 and (len(macd_hist) >= 2 and macd_hist[-1] < macd_hist[-2])

    # ── BOLL分析 ──────────────────────────────────────────────────────
    boll_upper, boll_mid, boll_lower = BOLL(closes, N=20, P=2)
    latest_upper = boll_upper[-1] if len(boll_upper) > 0 else 0
    latest_mid = boll_mid[-1] if len(boll_mid) > 0 else 0
    latest_lower = boll_lower[-1] if len(boll_lower) > 0 else 0
    boll_width = (latest_upper - latest_lower) / latest_mid if latest_mid > 0 else 0
    percent_b = (latest_close - latest_lower) / (latest_upper - latest_lower) if (latest_upper - latest_lower) > 0 else 0.5

    # BOLL状态
    boll_position = "mid"  # upper/mid/lower
    if percent_b > 0.8:
        boll_position = "upper"
    elif percent_b < 0.2:
        boll_position = "lower"

    # ── 均线分析 ──────────────────────────────────────────────────────
    ma5 = MA(closes, 5)[-1] if len(closes) >= 5 else latest_close
    ma10 = MA(closes, 10)[-1] if len(closes) >= 10 else latest_close
    ma20 = MA(closes, 20)[-1] if len(closes) >= 20 else latest_close
    ma60 = MA(closes, 60)[-1] if len(closes) >= 60 else latest_close

    ma_bullish = ma5 > ma10 > ma20  # 多头排列
    ma_bearish = ma5 < ma10 < ma20  # 空头排列
    price_above_ma20 = latest_close > ma20
    price_above_ma60 = latest_close > ma60

    # ── 成交量分析 ────────────────────────────────────────────────────
    vol_ma5 = sum(volumes[-5:]) / 5 if len(volumes) >= 5 else volumes[-1] if volumes else 0
    vol_ma20 = sum(volumes[-20:]) / 20 if len(volumes) >= 20 else volumes[-1] if volumes else 0
    vol_ratio = vol_ma5 / vol_ma20 if vol_ma20 > 0 else 1.0
    vol_expanding = vol_ratio > 1.2  # 放量
    vol_contracting = vol_ratio < 0.8  # 缩量

    # ── 综合评分 ──────────────────────────────────────────────────────
    score = 50  # 基础分

    # 缠论信号
    buy_1_count = sum(1 for m in result.mmds if m.mmd_type.value == "1buy")
    sell_1_count = sum(1 for m in result.mmds if m.mmd_type.value == "1sell")
    latest_mmd = max(result.mmds, key=lambda m: m.bi.index if m.bi else 0) if result.mmds else None

    if latest_mmd:
        if latest_mmd.mmd_type.value in ("1buy", "2buy"):
            score += 15
        elif latest_mmd.mmd_type.value in ("1sell", "2sell"):
            score -= 15
        # 置信度加成
        score += latest_mmd.confidence * 10
        score -= (1 - latest_mmd.confidence) * 5

    # MACD
    if macd_golden:
        score += 10
    elif macd_dead:
        score -= 10
    if macd_above_zero:
        score += 5
    else:
        score -= 5
    if macd_trending_up:
        score += 5
    elif macd_trending_down:
        score -= 5

    # BOLL
    if boll_position == "lower":
        score += 8
    elif boll_position == "upper":
        score -= 8

    # 均线
    if ma_bullish:
        score += 10
    elif ma_bearish:
        score -= 10
    if price_above_ma20 and price_above_ma60:
        score += 5
    elif not price_above_ma20 and not price_above_ma60:
        score -= 5

    # 成交量
    if vol_expanding and latest_close > opens[-1]:
        score += 5  # 放量上涨
    elif vol_expanding and latest_close < opens[-1]:
        score -= 5  # 放量下跌
    elif vol_contracting and abs(latest_close - opens[-1]) < latest_close * 0.01:
        score += 2  # 缩量横盘，观望

    score = max(0, min(100, score))

    # ── 操作建议 ──────────────────────────────────────────────────────
    if score >= 75:
        action = "strong_buy"
        action_label = "强烈买入"
        action_color = "#22c55e"
        reason = "多指标共振看涨：缠论买点确认 + MACD金叉 + 均线多头排列"
    elif score >= 60:
        action = "buy"
        action_label = "买入"
        action_color = "#4ade80"
        reason = "技术面偏多，可考虑分批建仓"
    elif score >= 45:
        action = "hold"
        action_label = "持有观察"
        action_color = "#f59e0b"
        reason = "方向不明确，建议观望或持有现有仓位"
    elif score >= 30:
        action = "sell"
        action_label = "卖出"
        action_color = "#f97316"
        reason = "技术面偏空，建议减仓或止损"
    else:
        action = "strong_sell"
        action_label = "强烈卖出"
        action_color = "#ef4444"
        reason = "多指标共振看跌，建议清仓回避"

    # ── 返回结果 ──────────────────────────────────────────────────────
    return {
        "symbol": symbol,
        "date": latest_date,
        "close": round(latest_close, 2),
        "score": round(score, 1),
        "action": action,
        "action_label": action_label,
        "action_color": action_color,
        "reason": reason,
        "chanlun": {
            "bi_count": len(result.bis),
            "zs_count": len(result.zss),
            "mmd_count": len(result.mmds),
            "buy_1_count": buy_1_count,
            "sell_1_count": sell_1_count,
            "latest_mmd": {
                "type": latest_mmd.mmd_type.value if latest_mmd else None,
                "confidence": round(latest_mmd.confidence, 2) if latest_mmd else None,
                "msg": latest_mmd.msg if latest_mmd else None,
            } if latest_mmd else None,
        },
        "macd": {
            "dif": round(latest_dif, 4),
            "dea": round(latest_dea, 4),
            "hist": round(latest_macd, 4),
            "golden_cross": macd_golden,
            "dead_cross": macd_dead,
            "above_zero": macd_above_zero,
            "trending": "up" if macd_trending_up else ("down" if macd_trending_down else "flat"),
        },
        "boll": {
            "upper": round(latest_upper, 2),
            "mid": round(latest_mid, 2),
            "lower": round(latest_lower, 2),
            "width": round(boll_width, 4),
            "percent_b": round(percent_b, 3),
            "position": boll_position,
        },
        "moving_averages": {
            "ma5": round(ma5, 2),
            "ma10": round(ma10, 2),
            "ma20": round(ma20, 2),
            "ma60": round(ma60, 2),
            "bullish_arrangement": ma_bullish,
            "bearish_arrangement": ma_bearish,
        },
        "volume": {
            "ratio": round(vol_ratio, 2),
            "expanding": vol_expanding,
            "contracting": vol_contracting,
        },
    }


@router.get("/diagnosis/quick")
async def quick_diagnosis(
    market: str = "SZ",
    code: str = "",
    client: Any = Depends(get_client),
) -> dict[str, Any]:
    """快速诊断接口（GET），方便浏览器直接访问。"""
    if not code:
        return {"error": "请提供股票代码"}
    req = StockIdentifier(market=market, code=code)
    return await diagnose_stock(req, client)
