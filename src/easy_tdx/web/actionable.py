"""可操作择时口径（V718 共享模块）。

把缠论信号翻译成用户能照做的建议（入场/止损/目标 + 人话 + 多级别递归确认 +
历史胜率）——stock-pick 看板与信号监控共用同一口径，保证任何入口的提醒
都是「可操作」的。
"""

from __future__ import annotations

from typing import Any


def _novice_advice(result: Any, verdict: dict[str, Any]) -> dict[str, Any]:
    """把缠论信号翻译成小白能照做的择时建议（入场/止损/目标 + 人话）。"""
    mmds = result.mmds
    if not mmds:
        return {
            "explanation": "暂无明显缠论买卖点，建议观望，等结构清晰再动手",
            "entry": None,
            "stop": None,
            "target": None,
            "position_note": "空仓等待也是一种操作",
        }
    last = mmds[-1]
    # 小白保护：低置信度已降级观望，不给具体入场价，避免误导。
    if verdict.get("action") == "观望":
        return {
            "explanation": "当前信号置信度偏低，先观察，等更明确的买卖点再动手",
            "entry": None,
            "stop": None,
            "target": None,
            "position_note": "别因为一个模糊信号就进场，空仓等待也是操作",
            "signal": verdict.get("signal"),
            "direction": None,
        }
    is_buy = "buy" in last.mmd_type.value
    bi = last.bi
    # V625: 信号缺少触发笔时不给具体价位（避免 entry=None 且止损/目标取错窗口）。
    if bi is None:
        return {
            "explanation": "该信号缺少触发笔，暂不给具体价位，建议观望",
            "entry": None,
            "stop": None,
            "target": None,
            "position_note": "结构不完整，先观察",
            "signal": verdict.get("signal"),
            "direction": None,
        }
    idx = bi.end.bar_index
    closes = [float(k.close) for k in result.klines]
    highs = [float(k.high) for k in result.klines]
    lows = [float(k.low) for k in result.klines]
    # 把索引夹在有效范围内，避免越界导致止损/目标取到错误窗口。
    idx = max(0, min(idx, len(closes) - 1))

    def _r(v: Any) -> float | None:
        return round(float(v), 2) if v is not None else None

    entry = (
        _r(closes[idx])
        if idx is not None and 0 <= idx < len(closes)
        else _r(bi.end.val if bi else None)
    )
    zs = last.zs
    if is_buy:
        lo = lows[max(0, (idx or 0) - 10) : (idx or 0) + 1]
        stop = _r(min(lo)) if lo else _r(zs.zd if zs else None)
        hi = highs[max(0, (idx or 0) - 60) : (idx or 0) + 1]
        target = _r(max(hi)) if hi else _r(zs.zg if zs else None)
        explanation = (
            f"出现{last.mmd_type.value}买点：参考买入价 {entry}；"
            f"若跌破 {stop} 先离场，目标先看 {target} 附近。"
        )
        position_note = "新手建议小仓位试仓，确认上涨再加，不要一次满仓"
    else:
        hi = highs[max(0, (idx or 0) - 10) : (idx or 0) + 1]
        stop = _r(max(hi)) if hi else _r(zs.zg if zs else None)
        lo = lows[max(0, (idx or 0) - 60) : (idx or 0) + 1]
        target = _r(min(lo)) if lo else _r(zs.zd if zs else None)
        explanation = (
            f"出现{last.mmd_type.value}卖点：参考卖出价 {entry}；"
            f"若重新站上 {stop} 说明转强，可等回落到 {target} 附近。"
        )
        position_note = "新手建议先减仓落袋，不要因小涨就追回"
    return {
        "explanation": explanation,
        "entry": entry,
        "stop": stop,
        "target": target,
        "position_note": position_note,
        "signal": verdict.get("signal"),
        "direction": "buy" if is_buy else "sell",
    }


# 小白保护阈值：低于该置信度的信号不直接给买卖建议，先观察。
_MIN_CONF = 0.6


def _verdict(mmds: list[Any]) -> dict[str, Any]:
    """根据最新三类买卖点给出择时结论（可解释、非黑盒、低置信度降级观望）。"""
    if not mmds:
        return {"action": "观望", "reason": "截至目标日无缠论买卖点信号", "direction": None}
    last = mmds[-1]
    typ = last.mmd_type.value
    conf = last.confidence or 0
    if conf < _MIN_CONF:
        return {
            "action": "观望",
            "signal": typ,
            "confidence": round(conf, 2),
            "reason": f"信号置信度偏低（{conf:.0%}），建议先观察，等更明确的买卖点",
            "direction": None,
        }
    if "buy" in typ:
        action, direction = "买入", "buy"
        reason = f"最新信号 {typ}（置信度 {conf:.0%}），可考虑分批建仓"
    elif "sell" in typ:
        action, direction = "卖出", "sell"
        reason = f"最新信号 {typ}（置信度 {conf:.0%}），建议减仓/离场"
    else:
        action, direction = "观望", None
        reason = f"最新信号 {typ}（置信度 {conf:.0%}），观察确认"
    return {
        "action": action,
        "signal": typ,
        "confidence": round(conf, 2),
        "reason": reason,
        "direction": direction,
    }


def _recursion_context(result: Any) -> dict[str, Any]:
    """多级别递归结构确认：返回已产出级别数与其中出现的最高级别买入信号。"""
    lv = getattr(result, "recursive_levels", [])
    if not lv:
        return {
            "depth_produced": 0,
            "latest": None,
            "note": "更高级别结构暂不足，建议结合笔级别信号执行，普通行情可用",
        }
    latest: dict[str, Any] | None = None
    # 从最高级别向低级别找第一个出现的更高级别买卖点信号作佐证。
    for i in range(len(lv) - 1, -1, -1):
        mmds = lv[i].mmds
        if mmds:
            m = mmds[-1]
            t = str(m.mmd_type.value)
            latest = {
                "level": i + 1,
                "signal": t,
                "direction": "buy" if "buy" in t else ("sell" if "sell" in t else "other"),
                "confidence": round(m.confidence or 0, 2),
                "date": str(m.bi.end.k.date)[:10] if m.bi else None,
            }
            break
    return {
        "depth_produced": len(lv),
        "latest": latest,
        "note": (
            f"存在{len(lv)}级递归结构；更高级别最新信号 {latest['signal']}"
            if latest
            else f"存在{len(lv)}级递归结构，但暂无更高级别买卖点信号"
        ),
    }


def season_position_note(season: dict[str, Any] | None) -> str:
    """四季仓位建议一句话（season 为 None 时给出中性提示）。"""
    if not season:
        return "四季数据暂不可用，建议按自身风险承受能力控制仓位"
    label = season.get("label") or season.get("season") or ""
    pr = season.get("position_range")
    action = season.get("action") or season.get("strategy") or ""
    if pr and len(pr) == 2:
        return f"{label}：建议仓位 {pr[0]}%~{pr[1]}%；{action}"
    return f"{label}：{action}" if action else label or "四季数据暂不可用"
