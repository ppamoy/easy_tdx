"""P1 长赢基本面选股 —— 树粮菜量化分类引擎（point-in-time，无未来函数）。

长赢理论三维：🌳 树（核心底仓）/ 🌾 粮（稳健收益）/ 🥬 菜（波段收益）。

打分原则：每只股票在目标日期 T 只使用「截至 T 已披露」的最新财报
（见 easy_tdx.fundamental.indicators.pick_report），输出三张可解释的打分明细，
取最高分类作为最终结论。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

# ── 分类常量 ────────────────────────────────────────────────────────────
TREE = "tree"
GRAIN = "grain"
VEGETABLE = "vegetable"

CATEGORY_LABELS = {
    TREE: "🌳 树型",
    GRAIN: "🌾 粮型",
    VEGETABLE: "🥬 菜型",
}

CATEGORY_DESCS = {
    TREE: "龙头护城河 + 高 ROE + 稳定成长：核心底仓",
    GRAIN: "稳定盈利 + 低负债 + 合理估值（高分红的）稳健收益",
    VEGETABLE: "高景气高增长 + 高弹性：波段收益",
}


@dataclass
class ScoreDetail:
    """单维打分明细。"""

    name: str
    score: float
    max: float
    reason: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "score": round(self.score, 1),
            "max": self.max,
            "reason": self.reason,
        }


@dataclass
class ScreenResult:
    """一只股票在目标日期的选股结论。"""

    code: str
    market: str
    category: str
    scores: dict[str, float]
    details: dict[str, list[ScoreDetail]]
    report_date: date | None
    indicators: dict[str, Any] = field(default_factory=dict)

    def label(self) -> str:
        return CATEGORY_LABELS.get(self.category, self.category)

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "market": self.market,
            "category": self.category,
            "label": self.label(),
            "description": CATEGORY_DESCS.get(self.category, ""),
            "scores": {k: round(v, 1) for k, v in self.scores.items()},
            "details": {k: [d.as_dict() for d in ds] for k, ds in self.details.items()},
            "report_date": str(self.report_date) if self.report_date else None,
            "indicators": self.indicators,
        }


def _pct(v: Any) -> float | None:
    """百分比数值（可能为 None）。"""
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _contrib(score: float, max_score: float, reason: str) -> ScoreDetail:
    return ScoreDetail(
        name=reason.split("：")[0][:12], score=score, max=max_score, reason=reason
    )


def score_tree(row: Any, pool_size: int) -> tuple[float, list[ScoreDetail]]:
    """🌳 树：龙头地位 + 高ROE + 稳定成长 + 护城河。"""
    total = 0.0
    details: list[ScoreDetail] = []

    roe = _pct(row.get("roe"))
    gross = _pct(row.get("gross_margin"))
    rev_yoy = _pct(row.get("rev_yoy"))
    np_yoy = _pct(row.get("np_yoy"))
    np = row.get("net_profit")
    assets = row.get("revenue")

    if np is not None and np > 0:
        total += 10
        details.append(_contrib(10, 10, "盈利为正（树的第一要义）"))
    else:
        details.append(_contrib(0, 10, "亏损/无净利润：不满足树条件"))
    if assets is not None and assets > 1e10:
        total += 10
        details.append(_contrib(10, 10, f"营收体量大（{assets / 1e8:.0f} 亿）"))
    else:
        details.append(_contrib(0, 10, "营收规模偏小"))

    if roe is not None:
        if roe >= 20:
            total += 30
            details.append(_contrib(30, 30, f"ROE {roe:.1f}%≥20%（极强）"))
        elif roe >= 15:
            total += 24
            details.append(_contrib(24, 30, f"ROE {roe:.1f}%≥15%（优秀）"))
        elif roe >= 10:
            total += 15
            details.append(_contrib(15, 30, f"ROE {roe:.1f}%≥10%（中等）"))
        else:
            total += 4
            details.append(_contrib(4, 30, f"ROE {roe:.1f}%<10%（不足）"))
    else:
        details.append(_contrib(0, 30, "无 ROE 数据"))

    g = 0.0
    if rev_yoy is not None and rev_yoy > 0:
        g += 1
    if np_yoy is not None and np_yoy > 0:
        g += 1
    total += g * 15
    details.append(
        _contrib(
            g * 15,
            30,
            f"增长：营收同比{rev_yoy if rev_yoy is not None else 0:.1f}% / "
            f"净利同比{np_yoy if np_yoy is not None else 0:.1f}%",
        )
    )

    if gross is not None:
        if gross >= 40:
            total += 20
            details.append(_contrib(20, 20, f"毛利率 {gross:.1f}%≥40%（强护城河）"))
        elif gross >= 25:
            total += 14
            details.append(_contrib(14, 20, f"毛利率 {gross:.1f}%≥25%"))
        else:
            total += 5
            details.append(_contrib(5, 20, f"毛利率 {gross:.1f}%<25%"))
    else:
        details.append(_contrib(0, 20, "无毛利率数据"))

    return min(total, 100), details


def score_grain(row: Any, pool_size: int) -> tuple[float, list[ScoreDetail]]:
    """🌾 粮：稳定盈利 + 低负债 + 现金流健康（分红字段暂缺，用 OCF 近似）。"""
    total = 0.0
    details: list[ScoreDetail] = []

    np = row.get("net_profit")
    ocf = row.get("ocf")
    debt = _pct(row.get("debt_ratio"))
    eps = row.get("eps")
    np_yoy = _pct(row.get("np_yoy"))

    if np is not None and np > 0:
        total += 20
        details.append(_contrib(20, 20, "净利润为正（粮的基础）"))
    else:
        details.append(_contrib(0, 20, "亏损：不满足粮条件"))
    if np_yoy is not None and np_yoy >= -10:
        total += 15
        details.append(_contrib(15, 15, f"净利同比 {np_yoy:.1f}% 未大幅下滑"))
    else:
        details.append(_contrib(0, 15, "净利大幅下滑/缺失"))

    if debt is not None:
        if debt <= 40:
            total += 25
            details.append(_contrib(25, 25, f"资产负债率 {debt:.1f}%≤40%（低杠杆）"))
        elif debt <= 60:
            total += 17
            details.append(_contrib(17, 25, f"资产负债率 {debt:.1f}%（中等）"))
        elif debt <= 75:
            total += 8
            details.append(_contrib(8, 25, f"资产负债率 {debt:.1f}%（偏高）"))
        else:
            total += 2
            details.append(_contrib(2, 25, f"资产负债率 {debt:.1f}%（高杠杆）"))
    else:
        details.append(_contrib(0, 25, "无负债数据"))

    if ocf is not None and ocf > 0:
        total += 20
        details.append(_contrib(20, 20, "经营现金流为正（可持续分红的基础）"))
    else:
        details.append(_contrib(0, 20, "经营现金流为负/缺失"))

    if eps is not None and eps > 0:
        total += 20
        details.append(_contrib(20, 20, f"每股收益 {eps:.2f} 元（有分红能力）"))
    else:
        details.append(_contrib(0, 20, "EPS 非正"))

    return min(total, 100), details


def score_vegetable(row: Any, pool_size: int) -> tuple[float, list[ScoreDetail]]:
    """🥬 菜：高景气高增长 + 高弹性。"""
    total = 0.0
    details: list[ScoreDetail] = []

    rev_yoy = _pct(row.get("rev_yoy"))
    np_yoy = _pct(row.get("np_yoy"))
    net_margin = _pct(row.get("net_margin"))
    np = row.get("net_profit")

    if rev_yoy is not None and rev_yoy >= 20:
        total += 35
        details.append(_contrib(35, 35, f"营收同比 {rev_yoy:.1f}%≥20%（高景气）"))
    elif rev_yoy is not None and rev_yoy >= 10:
        total += 22
        details.append(_contrib(22, 35, f"营收同比 {rev_yoy:.1f}%≥10%"))
    elif rev_yoy is not None and rev_yoy >= 0:
        total += 10
        details.append(_contrib(10, 35, f"营收同比 {rev_yoy:.1f}%（温和）"))
    else:
        details.append(_contrib(0, 35, "营收负增长/缺失"))

    if np_yoy is not None and np_yoy >= 30:
        total += 35
        details.append(_contrib(35, 35, f"净利同比 {np_yoy:.1f}%≥30%（爆发）"))
    elif np_yoy is not None and np_yoy >= 10:
        total += 20
        details.append(_contrib(20, 35, f"净利同比 {np_yoy:.1f}%（较快）"))
    else:
        details.append(_contrib(0, 35, "净利未见高增长"))

    if np is not None and np > 0 and net_margin is not None and net_margin > 0:
        total += 20
        details.append(_contrib(20, 20, f"盈利且净利率 {net_margin:.1f}%（符合菜的基本面）"))
    elif np is not None and np > 0:
        total += 10
        details.append(_contrib(10, 20, "盈利但净利率未披露/极低"))
    else:
        details.append(_contrib(0, 20, "亏损：需要更高增速来证明"))

    ocf = row.get("ocf")
    if ocf is not None and ocf > 0:
        total += 10
        details.append(_contrib(10, 10, "经营现金流为正"))
    else:
        details.append(_contrib(0, 10, "经营现金流非正"))

    return min(total, 100), details


def screen_stock(
    row: Any,
    *,
    pool_size: int = 1,
) -> ScreenResult | None:
    """对一只股票（已 point-in-time 裁剪的一期）做树粮菜打分。"""
    if row is None:
        return None
    code = str(row.get("code", ""))
    if not code:
        return None
    market = str(row.get("market", "SZ"))

    s_tree, d_tree = score_tree(row, pool_size)
    s_grain, d_grain = score_grain(row, pool_size)
    s_veg, d_veg = score_vegetable(row, pool_size)
    scores = {TREE: s_tree, GRAIN: s_grain, VEGETABLE: s_veg}
    category = max(scores, key=scores.get)

    ind = {
        "eps": row.get("eps"),
        "roe": row.get("roe"),
        "gross_margin": row.get("gross_margin"),
        "net_margin": row.get("net_margin"),
        "debt_ratio": row.get("debt_ratio"),
        "rev_yoy": row.get("rev_yoy"),
        "np_yoy": row.get("np_yoy"),
        "net_profit": row.get("net_profit"),
        "revenue": row.get("revenue"),
        "ocf": row.get("ocf"),
    }
    return ScreenResult(
        code=code,
        market=market,
        category=category,
        scores=scores,
        details={TREE: d_tree, GRAIN: d_grain, VEGETABLE: d_veg},
        report_date=row.get("report_date"),
        indicators=ind,
    )
