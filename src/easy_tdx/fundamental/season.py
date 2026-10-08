"""P1 长赢基本面选股 —— 历史时点四季周期判断。

复用 changying_chanlun 的四季信号框架（价格趋势 / 均线系统 / 波动率 / 量能），
但输入改为「截至目标日期 T 的市场指数日线」（杜绝未来函数）：只用 T 及之前
的 K 线计算，输出当时所处的季节与仓位建议。
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

import pandas as pd

# 与 changying/前端一致的季节定义
SEASONS = {"spring", "summer", "autumn", "winter", "unknown"}

SEASON_INFO: dict[str, dict[str, Any]] = {
    "spring": {
        "label": "春季·播种期",
        "color": "#4ade80",
        "description": "熊末牛初，估值见底，市场情绪极致绝望，行情在绝望中诞生",
        "strategy": "春播：分批逆向布局，精选优质成长标的，逐步建仓",
        "position_range": (30, 50),
        "action": "买入优质成长股，不恐慌割肉",
    },
    "summer": {
        "label": "夏季·成长期",
        "color": "#22c55e",
        "description": "牛市主升，赚钱效应扩散，行情在犹豫中发展，主线持续走强",
        "strategy": "夏长：坚定满仓持有，拥抱核心主线，杜绝频繁换股",
        "position_range": (80, 100),
        "action": "满仓持有核心标的，让利润奔跑",
    },
    "autumn": {
        "label": "秋季·收获期",
        "color": "#f59e0b",
        "description": "牛市末期，情绪狂热，估值透支，行情在乐观中见顶",
        "strategy": "秋收：分批减仓落袋，收缩战线，剔除劣质标的",
        "position_range": (20, 40),
        "action": "分批止盈，锁定收益",
    },
    "winter": {
        "label": "冬季·蛰伏期",
        "color": "#60a5fa",
        "description": "熊市主跌，恐慌蔓延，流动性收缩，普跌行情为主",
        "strategy": "冬藏：轻仓空仓为主，现金为王，耐心等待市场出清",
        "position_range": (0, 20),
        "action": "轻仓观望，保存本金",
    },
    "unknown": {
        "label": "分析中...",
        "color": "#94a3b8",
        "description": "数据不足，无法判断当前周期阶段",
        "strategy": "观望",
        "position_range": (0, 0),
        "action": "等待更多数据",
    },
}


@dataclass
class SeasonResult:
    season: str
    signals: dict[str, Any] = field(default_factory=dict)

    def label(self) -> str:
        label: str = SEASON_INFO.get(self.season, SEASON_INFO["unknown"])["label"]
        return label

    def info(self) -> dict[str, Any]:
        return SEASON_INFO.get(self.season, SEASON_INFO["unknown"])

    def as_dict(self) -> dict[str, Any]:
        info = self.info()
        return {
            "season": self.season,
            "label": info["label"],
            "color": info["color"],
            "description": info["description"],
            "strategy": info["strategy"],
            "position_range": list(info["position_range"]),
            "action": info["action"],
            "signals": self.signals,
        }


def _closes(
    dates: Sequence[Any],
    closes: Sequence[Any],
    target: date,
) -> tuple[list[date], list[float]]:
    """只保留 <= target 的 (date, close)，并按时间升序。"""
    pairs: list[tuple[date, float]] = []
    for d, c in zip(dates, closes):
        # ⚠️ V733 实测陷阱：``pd.Timestamp`` **是** ``datetime.date`` 的子类，
        # 所以原先的 ``isinstance(d, date)`` 会对 Timestamp 判 True 而**跳过
        # 转换**，随后 ``Timestamp <= date`` 直接 TypeError 崩
        # （实测：Cannot compare Timestamp with datetime.date）。
        # 现有调用方（pipeline.py:668/685）都先做了 ``.dt.date`` 才没炸，
        # 但任何传原始 Timestamp 的新调用方都会踩。改为显式排除 Timestamp。
        if isinstance(d, pd.Timestamp):
            dd = d.date()
        elif isinstance(d, datetime):
            dd = d.date()
        elif isinstance(d, date):
            dd = d
        else:
            dd = pd.to_datetime(d).date()
        if dd <= target and c == c:
            pairs.append((dd, float(c)))
    pairs.sort(key=lambda x: x[0])
    return [p[0] for p in pairs], [p[1] for p in pairs]


def _volumes(
    dates: Sequence[Any],
    volumes: Sequence[Any] | None,
    target: date,
) -> list[float]:
    """只保留 <= target 的量能，并按时间升序（与 _closes 同口径）。

    V731 修复：此前 `detect_season` 直接对**未过滤**的 volumes 取 `[-60:]`。
    收盘价是经 `_closes` 按 target 过滤的，量能却没有 —— 于是历史时点的
    「量能」信号读的是**序列最后 60 根**，即 target 之后的未来数据。
    实测：未来段量能暴涨时，vol_score2 从 0 变成 1、总分从 1 变成 2（春季→
    更热的判定），确实污染了四季结论。
    """
    if not volumes:
        return []
    pairs: list[tuple[date, float]] = []
    for d, v in zip(dates, volumes):
        if v is None or v != v:  # None / NaN
            continue
        dd = pd.to_datetime(d).date() if not isinstance(d, date) else d
        if dd <= target:
            pairs.append((dd, float(v)))
    pairs.sort(key=lambda x: x[0])
    return [p[1] for p in pairs]


def detect_season(
    dates: Sequence[Any],
    closes: Sequence[Any],
    target: date,
    *,
    volumes: Sequence[Any] | None = None,
) -> SeasonResult:
    """从截至 target 的指数日线判断四季。

    信号（与 changying_chanlun._update_season 对齐，纯向量计算）：
    - 价格趋势：60 日涨跌幅分档 → -2..2
    - 均线系统：MA20 与 MA60 关系 → -1..1
    - 波动率：近 20 日波动率相对近 60 日 → -1..1
    - 量能：近 5 日均量相对近 60 日均量 → -1..1

    总分四季区间：>=3 summer，>=1 spring，>=-1 autumn，else winter。
    """
    dts, cs = _closes(dates, closes, target)
    n = len(cs)
    sig = {"n_bars": n, "last_date": str(dts[-1]) if dts else None, "close": cs[-1] if cs else None}
    if n < 40:
        return SeasonResult(season="unknown", signals={**sig, "reason": "K线不足40根"})

    trend_60 = (
        (cs[-1] - cs[-60]) / cs[-60]
        if n >= 60 and cs[-60]
        else ((cs[-1] - cs[0]) / cs[0] if cs[0] else 0)
    )
    # 注意顺序：先判强跌（<-0.25 → -2）再判缓跌（<-0.08 → -1），
    # 否则 -2 分支永远不可达（旧实现把 -1 放在前面，强跌只会得 -1）。
    price_score = (
        2
        if trend_60 > 0.25
        else 1
        if trend_60 > 0.08
        else -2
        if trend_60 < -0.25
        else -1
        if trend_60 < -0.08
        else 0
    )

    ma20 = sum(cs[-20:]) / 20
    ma60 = sum(cs[-60:]) / 60 if n >= 60 else sum(cs) / n
    ma_ratio = ma20 / ma60 if ma60 else 1
    ma_score = 1 if ma_ratio > 1.05 else -1 if ma_ratio < 0.95 else 0

    def _stdev(xs: list[float]) -> float:
        if len(xs) < 2:
            return 0.0
        m = sum(xs) / len(xs)
        variance = sum((x - m) ** 2 for x in xs) / (len(xs) - 1)
        return math.sqrt(variance)

    rets = [cs[i] / cs[i - 1] - 1 for i in range(1, n) if cs[i - 1]]
    vol_20 = _stdev(rets[-20:]) if len(rets) >= 20 else _stdev(rets)
    vol_60 = _stdev(rets[-60:]) if len(rets) >= 60 else _stdev(rets)
    vol_score = 0
    if vol_60 > 0:
        vr = vol_20 / vol_60
        vol_score = -1 if vr > 1.3 else 1 if vr < 0.7 else 0

    vol_score2 = 0
    vs = _volumes(dates, volumes, target)  # V731：量能必须先按 target 过滤
    if len(vs) >= 60:
        vs = vs[-60:]
        if len(vs) >= 20:
            v5 = sum(vs[-5:]) / 5
            v60 = sum(vs) / len(vs)
            if v60 > 0:
                vol_score2 = 1 if v5 / v60 > 1.2 else -1 if v5 / v60 < 0.8 else 0

    total = price_score + ma_score + vol_score + vol_score2
    trend_20 = (cs[-1] - cs[-20]) / cs[-20] if n >= 20 and cs[-20] else 0
    sig.update(
        {
            "trend_60d_pct": round(trend_60 * 100, 2),
            "trend_20d_pct": round(trend_20 * 100, 2),
            "price_score": price_score,
            "ma_ratio": round(ma_ratio, 3),
            "ma_score": ma_score,
            "vol_score": vol_score,
            "vol_score2": vol_score2,
            "total_score": total,
        }
    )

    # 与 changying_chanlun 一致的季节映射：强分直接定季，
    # 中性分按近 20 日趋势方向翻转（历史时点无“当前季”，用趋势做方向）。
    if total >= 3:
        season = "summer"
    elif total >= 1:
        season = "spring"
    elif total <= -3:
        season = "winter"
    elif total <= -1:
        season = "autumn"
    elif trend_20 < -0.05:
        season = "autumn"
    elif trend_20 > 0.05:
        season = "spring"
    else:
        season = "spring"  # 中性且横盘：默认播种/等待
    return SeasonResult(season=season, signals=sig)


__all__ = ["SeasonResult", "detect_season", "SEASON_INFO", "SEASONS"]
