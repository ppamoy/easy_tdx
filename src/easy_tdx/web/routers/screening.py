"""长赢动态选股API路由。

功能：
1. 选择历史日期
2. 根据长赢模型筛选股票
3. 返回符合条件的股票列表
4. 支持后续缠论买卖点回测
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import pandas as pd
from fastapi import APIRouter, Depends

from easy_tdx.web.convert import category_from_str, market_from_str
from easy_tdx.web.deps import get_client

router = APIRouter(tags=["screening"])
logger = logging.getLogger(__name__)


@router.post("/screening/scan")
async def scan_stocks(
    req: dict[str, Any],
    client: Any = Depends(get_client),
) -> dict[str, Any]:
    """扫描股票，根据长赢模型筛选。

    请求参数：
    - date: 历史日期 (YYYY-MM-DD)
    - market: 市场 (SZ/SH)
    - min_klines: 最少K线数
    - season_filter: 是否过滤季节
    - stock_type: 股票类型 (tree/grain/vegetable/all)
    """

    date_str = req.get("date", "")
    market = req.get("market", "SZ")
    min_klines = req.get("min_klines", 100)
    season_filter = req.get("season_filter", True)
    stock_type = req.get("stock_type", "all")

    if not date_str:
        return {"error": "请提供历史日期", "stocks": []}

    # 解析日期
    try:
        target_date = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return {"error": "日期格式错误，请使用 YYYY-MM-DD", "stocks": []}

    # 获取股票列表
    stocks = await _get_stock_list(client, market)

    results = {
        "date": date_str,
        "market": market,
        "total_scanned": len(stocks),
        "qualified": [],
        "details": [],
    }

    # 扫描每只股票（限制数量避免超时）
    max_stocks = min(len(stocks), 30)  # 最多扫描30只
    results["total_scanned"] = max_stocks
    logger.info(f"开始扫描 {max_stocks} 只股票...")

    import time

    start_time = time.time()

    for i, stock in enumerate(stocks[:max_stocks]):
        try:
            stock_result = await _analyze_stock(client, market, stock, target_date, min_klines)
            if stock_result.get("valid"):
                # 根据长赢模型筛选
                if _pass_screening(stock_result, stock_type, season_filter):
                    results["qualified"].append(stock_result)
                else:
                    results["details"].append(
                        {
                            "code": stock,
                            "reason": stock_result.get("reason", "未通过筛选"),
                        }
                    )
        except Exception as e:
            logger.warning(f"扫描 {stock} 失败: {e}")
            continue

        # 每5只打印进度
        if (i + 1) % 5 == 0:
            elapsed = time.time() - start_time
            logger.info(f"已扫描 {i + 1}/{max_stocks} 只，耗时 {elapsed:.1f}s")

    elapsed_total = time.time() - start_time
    logger.info(f"扫描完成，总耗时 {elapsed_total:.1f}s")

    # 按质量排序
    results["qualified"].sort(key=lambda x: x.get("quality_score", 0), reverse=True)

    return results


@router.post("/screening/evaluate")
async def evaluate_stock(
    req: dict[str, Any],
    client: Any = Depends(get_client),
) -> dict[str, Any]:
    """评估单只股票的长赢质量。

    请求参数：
    - market: 市场
    - code: 股票代码
    - date: 历史日期
    """
    from easy_tdx.chanlun import ChanlunAnalyser
    from easy_tdx.chanlun.types import MMDType

    market = req.get("market", "SZ")
    code = req.get("code", "")
    date_str = req.get("date", "")

    if not code or not date_str:
        return {"error": "请提供股票代码和日期"}

    try:
        target_date = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return {"error": "日期格式错误"}

    # 获取数据
    df = await client.get_security_bars(
        market_from_str(market),
        code,
        category_from_str("DAY"),
        0,
        500,
    )

    if df is None or len(df) < 100:
        return {"error": "数据不足", "code": f"{market}{code}"}

    # 缠论分析
    analyser = ChanlunAnalyser(code=f"{market}{code}", frequency="DAILY")
    result = analyser.process_klines(df)

    # 计算质量分数
    score = _calc_quality_score(result, target_date)

    return {
        "code": f"{market}{code}",
        "date": date_str,
        "score": score,
        "chanlun": {
            "kline_count": len(result.klines),
            "bi_count": len(result.bis),
            "zs_count": len(result.zss),
            "mmd_count": len(result.mmds),
            "buy_1": sum(1 for m in result.mmds if m.mmd_type == MMDType.BUY_1),
            "sell_1": sum(1 for m in result.mmds if m.mmd_type == MMDType.SELL_1),
        },
        "classification": _classify_stock(result),
    }


async def _get_stock_list(client: Any, market: str) -> list[str]:
    """获取股票列表（使用预定义热门股票池，避免全市场扫描超时）。"""
    # 预定义的热门股票池（可根据需要扩展）
    HOT_STOCKS = {
        "SZ": [
            "000001",
            "000002",
            "000063",
            "000100",
            "000333",
            "000568",
            "000651",
            "000725",
            "000858",
            "002594",
            "300059",
            "300015",
            "300014",
            "300012",
            "300750",
        ],
        "SH": [
            "600000",
            "600004",
            "600009",
            "600010",
            "600011",
            "600016",
            "600028",
            "600030",
            "600036",
            "600048",
            "600519",
            "601318",
            "601398",
            "601398",
            "600900",
        ],
    }

    return HOT_STOCKS.get(market, [])


async def _analyze_stock(
    client: Any,
    market: str,
    code: str,
    target_date: datetime,
    min_klines: int,
) -> dict[str, Any]:
    """分析单只股票。"""
    from easy_tdx.chanlun import ChanlunAnalyser
    from easy_tdx.chanlun.types import MMDType

    # 获取数据
    df = await client.get_security_bars(
        market_from_str(market),
        code,
        category_from_str("DAY"),
        0,
        500,
    )

    if df is None or len(df) < min_klines:
        return {"valid": False, "reason": "数据不足"}

    # 检查目标日期是否有数据
    if "datetime" in df.columns:
        dates = pd.to_datetime(df["datetime"]).dt.date
        if target_date.date() not in dates:
            # 找最近的日期
            closest_idx = (dates - target_date.date()).abs().idxmin()
            if len(dates) - closest_idx > 30:  # 允许30天误差
                df = df.iloc[closest_idx:]
            else:
                return {"valid": False, "reason": "日期不匹配"}

    # 缠论分析
    analyser = ChanlunAnalyser(code=f"{market}{code}", frequency="DAILY")
    result = analyser.process_klines(df)

    # 统计买卖点
    buy_1s = [m for m in result.mmds if m.mmd_type == MMDType.BUY_1]
    sell_1s = [m for m in result.mmds if m.mmd_type == MMDType.SELL_1]
    buy_2s = [m for m in result.mmds if m.mmd_type == MMDType.BUY_2]
    sell_2s = [m for m in result.mmds if m.mmd_type == MMDType.SELL_2]

    # 计算质量分数
    quality_score = _calc_stock_quality(result)

    return {
        "valid": True,
        "code": code,
        "market": market,
        "symbol": f"{market}{code}",
        "kline_count": len(result.klines),
        "bi_count": len(result.bis),
        "zs_count": len(result.zss),
        "buy_1_count": len(buy_1s),
        "sell_1_count": len(sell_1s),
        "buy_2_count": len(buy_2s),
        "sell_2_count": len(sell_2s),
        "quality_score": quality_score,
        "latest_mmd": _get_latest_mmd(result),
        "classification": _classify_stock(result),
    }


def _v102_quality_bonus(mmd: Any) -> tuple[int, str]:
    """V428: 从 V102 信号质量评分卡计算选股加分。

    评分卡字段（mmd_v102._calc_signal_quality_scorecard）：
    overall_grade(A/B/C)、strength(strong/medium/weak)、overall_score(0-100)。
    返回 (加分, 理由)。
    """
    scorecard = getattr(mmd, "_signal_quality_scorecard", None) or {}
    grade = scorecard.get("overall_grade", "")
    strength = scorecard.get("strength", "")
    overall = scorecard.get("overall_score", 0.0)

    bonus = 0
    reasons: list[str] = []
    if grade == "A":
        bonus += 15
        reasons.append("V102评级A")
    elif grade == "B":
        bonus += 10
        reasons.append("V102评级B")
    elif grade == "C":
        bonus += 5
        reasons.append("V102评级C")

    if strength == "strong":
        bonus += 5
        reasons.append("强度strong")
    elif strength == "medium":
        bonus += 2
        reasons.append("强度medium")

    if overall >= 60:
        reasons.append(f"评分{overall:.0f}")
    return bonus, " ".join(reasons)


def _calc_stock_quality(result: Any) -> float:
    """计算股票质量分数（结构数量 + V102 信号质量）。"""
    score = 50  # 基础分

    # 笔的数量（越多越活跃）
    bi_count = len(result.bis)
    if bi_count >= 20:
        score += 15
    elif bi_count >= 10:
        score += 10
    elif bi_count >= 5:
        score += 5

    # 中枢数量（有中枢才有趋势）
    zs_count = len(result.zss)
    if zs_count >= 5:
        score += 15
    elif zs_count >= 3:
        score += 10
    elif zs_count >= 1:
        score += 5

    # 买卖点数量
    mmd_count = len(result.mmds)
    if mmd_count >= 5:
        score += 10
    elif mmd_count >= 2:
        score += 5

    # 背驰确认
    bc_count = len(result.bcs)
    if bc_count >= 3:
        score += 5

    # V428: 最新买卖点的 V102 信号质量加分 + 买入方向加分
    if result.mmds:
        latest = max(result.mmds, key=lambda m: m.bi.index if m.bi else 0)
        v102_bonus, _reason = _v102_quality_bonus(latest)
        score += v102_bonus
        if "buy" in latest.mmd_type.value:
            score += 5  # 买入信号优先

    return min(score, 100)


def _get_latest_mmd(result: Any) -> dict[str, Any] | None:
    """获取最新买卖点。"""
    if not result.mmds:
        return None

    latest = max(result.mmds, key=lambda m: m.bi.index if m.bi else 0)
    return {
        "type": latest.mmd_type.value,
        "date": latest.bi.end.k.date.strftime("%Y-%m-%d") if latest.bi else None,
        "price": latest.bi.low
        if latest.bi and latest.mmd_type.value.endswith("buy")
        else latest.bi.high
        if latest.bi
        else None,
        # V102 决策支持（条件264-267）
        "v102_signal_quality": getattr(latest, "_signal_quality_scorecard", None),
        "v102_decision_support": getattr(latest, "_decision_support", None),
        "v102_pattern_match": getattr(latest, "_historical_pattern_match", None),
    }


def _pass_screening(
    stock_result: dict[str, Any],
    stock_type: str,
    season_filter: bool,
) -> bool:
    """判断是否通过筛选。"""
    # 必须有买卖点信号
    if stock_result.get("buy_1_count", 0) == 0 and stock_result.get("sell_1_count", 0) == 0:
        return False

    # 质量分数要求
    if stock_result.get("quality_score", 0) < 60:
        return False

    return True


def _classify_stock(result: Any) -> str:
    """分类股票类型。"""
    bi_count = len(result.bis)
    zs_count = len(result.zss)

    if bi_count >= 15 and zs_count >= 5:
        return "tree"  # 树型企业
    elif bi_count >= 10 and zs_count >= 3:
        return "grain"  # 粮型企业
    else:
        return "vegetable"  # 菜型企业


def _calc_quality_score(result: Any, target_date: datetime) -> float:
    """计算质量分数。"""
    score = 50

    # 根据最近买卖点评分
    if result.mmds:
        latest = max(result.mmds, key=lambda m: m.bi.index if m.bi else 0)
        if latest.mmd_type.value.endswith("buy"):
            score += 20
        else:
            score += 10

    # 根据中枢数量评分
    score += min(len(result.zss) * 5, 20)

    return min(score, 100)


@router.post("/screening/verify")
async def verify_screening(
    req: dict[str, Any],
    client: Any = Depends(get_client),
) -> dict[str, Any]:
    from easy_tdx.backtest.screening_verify import compute_screening_verify

    date_str = str(req.get("date", ""))
    symbols = req.get("symbols") or []
    selected = req.get("selected") or []
    market = str(req.get("market", "SZ")).upper()[:2]

    if not date_str or not symbols:
        return {"error": "请提供选股日期和扫描池股票列表", "horizons": {}, "verdict": ""}
    try:
        datetime.strptime(date_str, "%Y-%m-%d")  # noqa: DTZ007 - 校验格式即可
    except ValueError:
        return {"error": "日期格式错误，请使用 YYYY-MM-DD", "horizons": {}, "verdict": ""}

    def _norm(sym: str) -> str:
        """规范化为 市场:6位代码（兼容 SZ:000001 / SZ000001 / 000001）。"""
        if ":" in sym:
            m, c = sym.split(":", 1)
        elif len(sym) == 6:
            m = "SH" if sym.startswith("6") else market
            c = sym
        else:
            m = sym[:2].upper()
            c = sym[2:]
        return f"{m.upper()[:2]}:{c.zfill(6)}"

    symbols_canon = [_norm(s) for s in symbols]
    selected_codes = {_norm(s).split(":", 1)[1] for s in selected}
    # 池内被选中的集合（按代码匹配，兼容前缀差异）
    selected_in_pool = [s for s in symbols_canon if s.split(":", 1)[1] in selected_codes]

    bars_by_symbol: dict[str, dict[str, Any]] = {}
    for sym in symbols_canon:
        m, code = sym.split(":", 1)
        try:
            df = await client.get_security_bars(
                market_from_str(m), code, category_from_str("DAY"), 0, 400
            )
        except Exception:  # noqa: BLE001
            continue
        if df is None or len(df) < 2:
            continue
        dt_col = "datetime" if "datetime" in df.columns else "date"
        bars_by_symbol[sym] = {
            "datetime": [str(d)[:10] for d in df[dt_col].tolist()],
            "close": [float(c) for c in df["close"].tolist()],
        }

    if not bars_by_symbol:
        return {"error": "未能取到池内任何股票的行情", "horizons": {}, "verdict": ""}

    report = compute_screening_verify(
        bars_by_symbol,
        selected_in_pool,
        date_str,
    )
    report["selected_matched"] = len(selected_in_pool)
    return report
