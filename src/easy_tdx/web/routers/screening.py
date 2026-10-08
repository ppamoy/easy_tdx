"""长赢动态选股API路由。

功能：
1. 选择历史日期
2. 根据长赢模型筛选股票
3. 返回符合条件的股票列表
4. 支持后续缠论买卖点回测
"""

from __future__ import annotations

import logging
import math
from datetime import datetime
from typing import Any

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException

from easy_tdx.web.deps import get_client, get_mac_client_optional
from easy_tdx.web.klines import fetch_qfq_klines

router = APIRouter(tags=["screening"])
logger = logging.getLogger(__name__)


@router.post("/screening/scan")
async def scan_stocks(
    req: dict[str, Any],
    client: Any = Depends(get_client),
    mac_client: Any | None = Depends(get_mac_client_optional),
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
            stock_result = await _analyze_stock(
                client, mac_client, market, stock, target_date, min_klines
            )
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
    mac_client: Any | None = Depends(get_mac_client_optional),
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
        # V719: 参数错误统一 400（此前 200 + {"error": ...}，客户端会把失败当成功）
        raise HTTPException(status_code=400, detail="请提供股票代码和日期")

    try:
        target_date = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="日期格式错误，请使用 YYYY-MM-DD") from None

    # 获取数据（MAC 优先 + QFQ，标准 TDX 失效时仍可用）
    df = await fetch_qfq_klines(
        mac_client,
        client,
        market,
        code,
        "DAY",
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
            "600887",
            "600900",
        ],
    }

    return HOT_STOCKS.get(market, [])


async def _analyze_stock(
    client: Any,
    mac_client: Any | None,
    market: str,
    code: str,
    target_date: datetime,
    min_klines: int,
) -> dict[str, Any]:
    """分析单只股票。"""
    from easy_tdx.chanlun import ChanlunAnalyser
    from easy_tdx.chanlun.types import MMDType

    # 获取数据（MAC 优先 + QFQ，标准 TDX 失效时仍可用）
    df = await fetch_qfq_klines(
        mac_client,
        client,
        market,
        code,
        "DAY",
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
        "symbol": f"{market}:{code}",  # V721: D14 统一全站「市场:代码」口径（原 SZ000001）
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


def _latest_mmd_obj(result: Any) -> Any | None:
    """V454: 取最新买卖点对象（按 bi.index 最大），无则返回 None。"""
    if not result.mmds:
        return None
    return max(result.mmds, key=lambda m: m.bi.index if m.bi else 0)


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


def _v102_rr_bonus(mmd: Any) -> tuple[int, str]:
    """V437: 从 V102 决策支持的风险回报比计算选股加分。

    decision_support 字段（mmd_v102._calc_decision_support_enhanced）：
    risk_reward_ratio（风险回报比，>=2.0 为优秀交易计划）。
    返回 (加分, 理由)。
    """
    decision = getattr(mmd, "_decision_support", None) or {}
    rr = decision.get("risk_reward_ratio")
    if rr is None:
        return 0, ""
    rr_f = float(rr)
    if rr_f >= 2.0:
        return 10, f"RR={rr_f:.1f}"
    if rr_f >= 1.5:
        return 7, f"RR={rr_f:.1f}"
    if rr_f >= 1.0:
        return 3, f"RR={rr_f:.1f}"
    return 0, f"RR={rr_f:.1f}"


def _log1p(x: int) -> float:
    """log(1+x) 的轻量实现（避免为一个分数把 numpy 引进 web 层）。"""
    try:
        return math.log1p(max(0, int(x)))
    except (TypeError, ValueError):
        return 0.0


def _calc_stock_quality(result: Any) -> float:
    """计算股票质量分数（结构数量 + V102 信号质量）。

    ⚠️ V733 五之二十六：原实现是**阶梯式**加分（bi>=20 加 15 分，……）
       最后 `min(score, 100)` 封顶。实测 500 根 K 线下
       **57/60 = 95% 的股票都拿满分 100，全场只有 3 个不同取值**。
       而端点用它 `sort(key=quality_score)` 再截 `top_n`
       ⇒ **"取前 N 只"实际等于"随便取前 N 只"，排序形同虚设**。
       实测质量分 vs 未来 20 日收益 Spearman ρ=+0.13、p=0.16 ⇒ 排不出。

    改法：阶梯 → **连续递增**（log1p 压缩，"结构越多越好"不会线性爆掉），
       封顶只作用在**加分项**上，保留连续基础分。
    ⚠️ 这**只修"分数区分不出股票"这个缺陷**，
       **不代表改完就能选股赚钱**——五之二十五实测两种口径都选不出超额。
       这里刻意**不改动"买卖点结构密度"这个底层口径**：
       重新标定权重是更大的改动，且必须重做前瞻验证才能下结论。
    """
    score = 50.0  # 基础分

    # 结构数量：连续递增（对数压缩），不再阶梯跳变。
    # ⚠️ 系数是**从实测分布反推**的，不是拍脑袋：
    #    80 只 500 根K线下 笔 p10=106/中位=117、 中枢 16/18、 买卖点 34/42、 背驰 18/22。
    #    目标是让**中位数落在该项上限的 ~60%**，这样上下都有区分空间。
    #    （第一版我随手用 5.0/7.0/5.0/2.5，结果 log1p(117)*5=24 远超上限 15，
    #      **照样全顶格**——改了等于没改。还是得先量数据。）
    bi_count = len(result.bis)
    score += min(15.0, 1.9 * _log1p(bi_count))  # 笔越多越活跃
    zs_count = len(result.zss)
    score += min(15.0, 3.1 * _log1p(zs_count))  # 中枢数量
    mmd_count = len(result.mmds)
    score += min(10.0, 1.6 * _log1p(mmd_count))  # 买卖点数量
    bc_count = len(result.bcs)
    score += min(5.0, 1.0 * _log1p(bc_count))  # 背驰确认

    # V428/V437: 最新买卖点的 V102 信号质量 + 风险回报比 + 买入方向加分
    latest = _latest_mmd_obj(result)
    if latest is not None:
        v102_bonus, _reason = _v102_quality_bonus(latest)
        score += v102_bonus
        rr_bonus, _rr_reason = _v102_rr_bonus(latest)
        score += rr_bonus
        if "buy" in latest.mmd_type.value:
            score += 5  # 买入信号优先

    return min(score, 100)


def _is_buy_signal(mmd_type_value: str) -> bool:
    """V429: 判断买卖点类型是否为买入方向。

    用「包含 buy」而非 endswith——endswith 会漏判类二买（2buy_s）。
    """
    return "buy" in mmd_type_value


def _get_latest_mmd(result: Any) -> dict[str, Any] | None:
    """获取最新买卖点。"""
    latest = _latest_mmd_obj(result)
    if latest is None:
        return None
    return {
        "type": latest.mmd_type.value,
        "date": latest.bi.end.k.date.strftime("%Y-%m-%d") if latest.bi else None,
        "price": latest.bi.low
        if latest.bi and _is_buy_signal(latest.mmd_type.value)
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

    # 分类过滤（tree/grain/vegetable）
    if stock_type != "all" and stock_result.get("classification") != stock_type:
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
    latest = _latest_mmd_obj(result)
    if latest is not None:
        if _is_buy_signal(latest.mmd_type.value):
            score += 20
        else:
            score += 10

    # 根据中枢数量评分
    score += min(len(result.zss) * 5, 20)

    return min(score, 100)


# ════════════════════════════════════════════════════════════════════════
# 缠论原著选股（结构驱动，非长赢模型）
# ════════════════════════════════════════════════════════════════════════


def _chanlun_trend_direction(result: Any) -> str | None:
    """取线段(更高一级)趋势方向：'up' / 'down' / None。

    用最后一段已完成线段的方向。线段交替向上向下，最后一段的方向代表
    当前走势方向。
    """
    xds = getattr(result, "xds", None) or []
    done = [x for x in xds if getattr(x, "is_done", None) and x.is_done()]
    if not done:
        done = xds
    if not done:
        return None
    d = getattr(
        getattr(done[-1], "direction", None), "value", str(getattr(done[-1], "direction", ""))
    )
    return str(d).lower() or None


def _chanlun_zs_position(result: Any, close: float | None = None) -> str | None:
    """当前价相对最后中枢的位置：'above' / 'below' / 'inside' / None。"""
    zss = getattr(result, "zss", None) or []
    if not zss or close is None:
        return None
    z = zss[-1]
    # 中枢用 zg(中枢高)/zd(中枢低) 表示区间；兼容 high/low
    hi = getattr(z, "zg", None) or getattr(z, "high", None)
    lo = getattr(z, "zd", None) or getattr(z, "low", None)
    if hi is None or lo is None:
        return None
    if close > float(hi):
        return "above"
    if close < float(lo):
        return "below"
    return "inside"


def _chanlun_has_beichi(result: Any) -> bool:
    """是否有背驰确认。"""
    bcs = getattr(result, "bcs", None) or []
    return len(bcs) > 0


def _chanlun_latest_signal(result: Any) -> dict[str, Any] | None:
    """最新买卖点信息（用于选股筛选）。"""
    latest = _latest_mmd_obj(result)
    if latest is None:
        return None
    mmd_val = latest.mmd_type.value
    return {
        "type": mmd_val,
        "is_buy": "buy" in mmd_val,
        "date": latest.bi.end.k.date.strftime("%Y-%m-%d") if latest.bi else None,
        "price": (latest.bi.low if "buy" in mmd_val else latest.bi.high) if latest.bi else None,
        "confidence": round(float(latest.confidence), 4),
    }


def _chanlun_screen(
    result: Any,
    criteria: dict[str, Any],
    close: float | None = None,
) -> tuple[bool, dict[str, Any]]:
    """按缠论结构条件筛选单只股票。

    criteria 支持：
    - signal_type: "1buy"/"2buy"/"3buy"/"any_buy"/"1sell"/"any" (默认 "any_buy")
    - trend: "up"/"down"/"any" (默认 "any")
    - zs_position: "above"/"below"/"inside"/"any" (默认 "any")
    - has_beichi: bool (默认 False)
    - min_zs_count: int (默认 0)
    - min_quality: int (默认 0)
    """
    sig_type = criteria.get("signal_type", "any_buy")
    trend_req = criteria.get("trend", "any")
    has_bc = bool(criteria.get("has_beichi", False))
    min_zs = int(criteria.get("min_zs_count", 0) or 0)
    min_q = int(criteria.get("min_quality", 0) or 0)
    zs_pos_req = criteria.get("zs_position", "any")

    latest = _chanlun_latest_signal(result)
    trend = _chanlun_trend_direction(result)
    zs_pos = _chanlun_zs_position(result, close)
    bc = _chanlun_has_beichi(result)
    quality = _calc_stock_quality(result)

    details = {
        "latest_signal": latest,
        "trend": trend,
        "zs_position": zs_pos,
        "has_beichi": bc,
        "quality_score": quality,
        "bi_count": len(getattr(result, "bis", []) or []),
        "zs_count": len(getattr(result, "zss", []) or []),
        "bc_count": len(getattr(result, "bcs", []) or []),
        "classification": _classify_stock(result),
    }  # type: dict[str, Any]

    # 信号类型过滤
    if sig_type != "any":
        if latest is None:
            return False, details
        lt = latest["type"]
        if sig_type == "any_buy":
            if not latest["is_buy"]:
                return False, details
        elif sig_type == "1sell":
            if lt != "1sell":
                return False, details
        elif lt != sig_type:
            return False, details

    # 走势方向过滤
    if trend_req != "any" and trend != trend_req:
        return False, details

    # 中枢位置过滤
    if zs_pos_req != "any" and zs_pos != zs_pos_req:
        return False, details

    # 背驰过滤
    if has_bc and not bc:
        return False, details

    # 中枢数量过滤
    if details["zs_count"] < min_zs:
        return False, details

    # 质量分过滤
    if quality < min_q:
        return False, details

    return True, details


@router.post("/screening/chanlun-scan")
async def chanlun_scan(
    req: dict[str, Any],
    client: Any = Depends(get_client),
    mac_client: Any | None = Depends(get_mac_client_optional),
) -> dict[str, Any]:
    """缠论原著选股扫描。

    按缠论结构条件（买卖点类型、走势方向、中枢位置、背驰）筛选股票，
    以缠论为准；可选叠加长赢模型过滤。

    请求参数：
    - codes: 指定股票代码列表（不传则自动取市场前 30 只）
    - market: 市场 (SZ/SH，默认 SZ)
    - criteria: 筛选条件 dict（见 _chanlun_screen）
    - combine_changying: 是否叠加长赢过滤 (默认 False)
    - stock_type: 长赢类型 (tree/grain/vegetable/all，combine_changying=True 时生效)
    - top_n: 返回前 N 只 (默认 10)
    """
    from easy_tdx.chanlun import ChanlunAnalyser

    market = req.get("market", "SZ")
    codes = req.get("codes") or []
    criteria = req.get("criteria", {})
    combine_changying = bool(req.get("combine_changying", False))
    stock_type = req.get("stock_type", "all")
    top_n = int(req.get("top_n", 10) or 10)

    # 获取股票列表
    if codes:
        stocks = [str(c).zfill(6) for c in codes]
    else:
        stocks = await _get_stock_list(client, market)
        stocks = stocks[:30]

    results = {
        "market": market,
        "total_scanned": len(stocks),
        "qualified": [],
        "errors": [],
    }

    import time

    start = time.time()

    for i, code in enumerate(stocks):
        try:
            df = await fetch_qfq_klines(mac_client, client, market, code, "DAY", 0, 500)
            if df is None or len(df) < 100:
                continue

            analyser = ChanlunAnalyser(code=f"{market}{code}", frequency="DAILY")
            result = analyser.process_klines(df)
            close = float(df["close"].iloc[-1])

            passes, details = _chanlun_screen(result, criteria, close)

            # 可选：叠加长赢过滤
            if passes and combine_changying:
                stock_result = {
                    "buy_1_count": 1 if details["latest_signal"] else 0,
                    "quality_score": details["quality_score"],
                    "classification": details["classification"],
                }
                if not _pass_screening(stock_result, stock_type, True):
                    passes = False

            if passes:
                results["qualified"].append(
                    {
                        "code": code,
                        "symbol": f"{market}:{code}",
                        "close": round(close, 2),
                        **details,
                    }
                )
        except Exception as e:  # noqa: BLE001
            results["errors"].append({"code": code, "error": str(e)})
            continue

        if (i + 1) % 5 == 0:
            logger.info(f"缠论选股: 已扫描 {i + 1}/{len(stocks)}")

    # 按质量分排序
    results["qualified"].sort(key=lambda x: x.get("quality_score", 0), reverse=True)
    results["qualified"] = results["qualified"][:top_n]
    results["elapsed"] = round(time.time() - start, 1)

    return results


@router.post("/screening/verify")
async def verify_screening(
    req: dict[str, Any],
    client: Any = Depends(get_client),
    mac_client: Any | None = Depends(get_mac_client_optional),
) -> dict[str, Any]:
    """选股结果前瞻收益验证（选中 vs 池平均）。

    请求参数：
    - date: 选股日 (YYYY-MM-DD)
    - symbols: 扫描池股票列表（兼容 ``SZ:000001`` / ``SZ000001`` / ``000001``）
    - selected: 被选中的股票列表（格式同 symbols）
    - market: 前端传来的市场 (SZ/SH)。**当前实现不读它**：裸 6 位代码统一走
      ``_market_from_code`` 按前缀推断（与前端 ``detectMarket`` 同口径，
      避免北交所/9 开头被误判），仅保留该键以兼容既有请求体。
    """
    from easy_tdx.backtest.screening_verify import compute_screening_verify

    date_str = str(req.get("date", ""))
    symbols = req.get("symbols") or []
    selected = req.get("selected") or []

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
            # V532: 6 位裸代码用统一市场推断（与前端 detectMarket / sina / gpcw
            # 口径一致），不再「6→SH 其余→market」误判北交所/9 开头
            from easy_tdx.fundamental.indicators import _market_from_code

            m = _market_from_code(sym)
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
            df = await fetch_qfq_klines(mac_client, client, m, code, "DAY", 0, 400)
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
