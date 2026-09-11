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

# V561: 粮型「资产负债率」档位阈值（%）——低杠杆 / 中等 / 偏高 / 高杠杆
_DEBT_LOW = 40.0
_DEBT_MED = 60.0
_DEBT_HIGH = 75.0

# V562: 树型「ROE」档位阈值（%）——极强 / 优秀 / 中等 / 不足
_ROE_EXCELLENT = 20.0
_ROE_GOOD = 15.0
_ROE_MED = 10.0

# V563: 树型「营收体量」阈值（年化元）与「毛利率」档位阈值（%）
_TREE_REVENUE_MIN = 1e10  # 100 亿
_GROSS_MOAT = 40.0
_GROSS_MED = 25.0

# V564: 菜型「营收/净利同比」档位阈值（%）
_REV_HIGH = 20.0
_REV_MED = 10.0
_NP_BOOM = 30.0
_NP_FAST = 10.0


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


def _annualize(v: float | None, report_date: Any) -> float | None:
    """V507/V517/V537: 把年初至今累计值按报告期月数年化（ROE/营收等）。

    委托给 ``indicators.annualize_ytd`` 共享实现（V517 消除与 pipeline 的重复）。
    V537 由 ``_annualize_pct`` 更名——该函数同时用于 ROE（百分数）与营收（绝对值），
    「pct」命名有误导。
    """
    from easy_tdx.fundamental.indicators import annualize_ytd

    return annualize_ytd(v, report_date)


# V537: 保留旧名作为别名，兼容历史导入
_annualize_pct = _annualize


def _contrib(score: float, max_score: float, reason: str) -> ScoreDetail:
    return ScoreDetail(name=reason.split("：")[0][:12], score=score, max=max_score, reason=reason)


def score_tree(row: Any, pool_size: int) -> tuple[float, list[ScoreDetail]]:
    """🌳 树：龙头地位 + 高ROE + 稳定成长 + 护城河。"""
    total = 0.0
    details: list[ScoreDetail] = []

    roe = _annualize(_pct(row.get("roe")), row.get("report_date"))
    gross = _pct(row.get("gross_margin"))
    rev_yoy = _pct(row.get("rev_yoy"))
    np_yoy = _pct(row.get("np_yoy"))
    np = row.get("net_profit")
    # V522: 营收同为年初至今累计值，一季报按报告期年化后再判「体量大」，
    # 避免用单季营收低估龙头规模（如年营收 40 亿的公司 Q1 只 10 亿被误判「偏小」）
    revenue = _annualize(_pct(row.get("revenue")), row.get("report_date"))

    if np is not None and np > 0:
        total += 10
        details.append(_contrib(10, 10, "盈利为正（树的第一要义）"))
    else:
        details.append(_contrib(0, 10, "亏损/无净利润：不满足树条件"))
    if revenue is not None and revenue > _TREE_REVENUE_MIN:
        total += 10
        # V543: 营收为年化口径（V522），明示「年化」避免与单季营收混淆
        details.append(_contrib(10, 10, f"营收体量大（年化 {revenue / 1e8:.0f} 亿）"))
    else:
        # V556: 「偏小」也给出年化营收数值，便于用户理解为何被判「偏小」
        rev_suffix = f"（年化 {revenue / 1e8:.0f} 亿）" if revenue is not None else ""
        details.append(_contrib(0, 10, f"营收规模偏小{rev_suffix}"))

    if roe is not None:
        # V547: ROE 为年化口径（V507），明示「年化」避免与单季 ROE 混淆
        if roe >= _ROE_EXCELLENT:
            total += 30
            details.append(_contrib(30, 30, f"年化ROE {roe:.1f}%≥{_ROE_EXCELLENT:.0f}%（极强）"))
        elif roe >= _ROE_GOOD:
            total += 24
            details.append(_contrib(24, 30, f"年化ROE {roe:.1f}%≥{_ROE_GOOD:.0f}%（优秀）"))
        elif roe >= _ROE_MED:
            total += 15
            details.append(_contrib(15, 30, f"年化ROE {roe:.1f}%≥{_ROE_MED:.0f}%（中等）"))
        else:
            total += 4
            details.append(_contrib(4, 30, f"年化ROE {roe:.1f}%<{_ROE_MED:.0f}%（不足）"))
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
        if gross >= _GROSS_MOAT:
            total += 20
            details.append(_contrib(20, 20, f"毛利率 {gross:.1f}%≥{_GROSS_MOAT:.0f}%（强护城河）"))
        elif gross >= _GROSS_MED:
            total += 14
            details.append(_contrib(14, 20, f"毛利率 {gross:.1f}%≥{_GROSS_MED:.0f}%"))
        else:
            total += 5
            details.append(_contrib(5, 20, f"毛利率 {gross:.1f}%<{_GROSS_MED:.0f}%"))
    else:
        details.append(_contrib(0, 20, "无毛利率数据"))

    return min(total, 100), details


def score_grain(row: Any, pool_size: int) -> tuple[float, list[ScoreDetail]]:
    """🌾 粮：稳定盈利 + 低负债 + 现金流健康（分红字段暂缺，用 OCF 近似）。"""
    total = 0.0
    details: list[ScoreDetail] = []

    np = row.get("net_profit")
    # V539: 分红能力用「每股经营现金流」更直接（每股分红基础），缺省回退总量口径
    ocf = row.get("ocf_ps") if row.get("ocf_ps") is not None else row.get("ocf")
    debt = _pct(row.get("debt_ratio"))
    # V544: 每股收益年化后展示（分红能力按年计，一季报单季 EPS 会低估年度分红能力）
    eps = _annualize(_pct(row.get("eps")), row.get("report_date"))
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
        if debt <= _DEBT_LOW:
            total += 25
            details.append(_contrib(25, 25, f"资产负债率 {debt:.1f}%≤{_DEBT_LOW:.0f}%（低杠杆）"))
        elif debt <= _DEBT_MED:
            total += 17
            details.append(_contrib(17, 25, f"资产负债率 {debt:.1f}%（中等）"))
        elif debt <= _DEBT_HIGH:
            total += 8
            details.append(_contrib(8, 25, f"资产负债率 {debt:.1f}%（偏高）"))
        else:
            total += 2
            details.append(_contrib(2, 25, f"资产负债率 {debt:.1f}%（高杠杆）"))
    else:
        details.append(_contrib(0, 25, "无负债数据"))

    if ocf is not None and ocf > 0:
        total += 20
        details.append(_contrib(20, 20, "每股经营现金流为正（可持续分红的基础）"))
    else:
        details.append(_contrib(0, 20, "每股经营现金流为负/缺失"))

    if eps is not None and eps > 0:
        total += 20
        details.append(_contrib(20, 20, f"每股收益（年化）{eps:.2f} 元（有分红能力）"))
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

    if rev_yoy is not None and rev_yoy >= _REV_HIGH:
        total += 35
        details.append(_contrib(35, 35, f"营收同比 {rev_yoy:.1f}%≥{_REV_HIGH:.0f}%（高景气）"))
    elif rev_yoy is not None and rev_yoy >= _REV_MED:
        total += 22
        details.append(_contrib(22, 35, f"营收同比 {rev_yoy:.1f}%≥{_REV_MED:.0f}%"))
    elif rev_yoy is not None and rev_yoy >= 0:
        total += 10
        details.append(_contrib(10, 35, f"营收同比 {rev_yoy:.1f}%（温和）"))
    else:
        details.append(_contrib(0, 35, "营收负增长/缺失"))

    if np_yoy is not None and np_yoy >= _NP_BOOM:
        total += 35
        details.append(_contrib(35, 35, f"净利同比 {np_yoy:.1f}%≥{_NP_BOOM:.0f}%（爆发）"))
    elif np_yoy is not None and np_yoy >= _NP_FAST:
        total += 20
        details.append(_contrib(20, 35, f"净利同比 {np_yoy:.1f}%（较快）"))
    elif np_yoy is not None and np_yoy >= 0:
        # V555: 区分「正增长但不够高」与「负增长」（原两者同判 0 分）
        total += 5
        details.append(_contrib(5, 35, f"净利同比 {np_yoy:.1f}%（正增长）"))
    else:
        details.append(_contrib(0, 35, "净利负增长/缺失"))

    if np is not None and np > 0 and net_margin is not None and net_margin > 0:
        total += 20
        details.append(_contrib(20, 20, f"盈利且净利率 {net_margin:.1f}%（符合菜的基本面）"))
    elif np is not None and np > 0:
        total += 10
        details.append(_contrib(10, 20, "盈利但净利率未披露/极低"))
    else:
        details.append(_contrib(0, 20, "亏损：需要更高增速来证明"))

    ocf = row.get("ocf_ps") if row.get("ocf_ps") is not None else row.get("ocf")
    if ocf is not None and ocf > 0:
        total += 10
        details.append(_contrib(10, 10, "每股经营现金流为正"))
    else:
        details.append(_contrib(0, 10, "每股经营现金流非正"))

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
    # V549: 同分显式优先「树」>「粮」>「菜」，不依赖 dict 插入顺序
    _order = {TREE: 0, GRAIN: 1, VEGETABLE: 2}
    category = max(scores, key=lambda k: (scores[k], -_order[k]))

    ind = {
        # V560/V565: 透出报告期，作为「年化」字段的取数上下文（一季报年化因子 ×4 的依据）；
        # 转为字符串与 as_dict 外层 report_date 口径一致（避免 date 对象直接 JSON 序列化）
        "report_date": str(row.get("report_date")) if row.get("report_date") else None,
        "eps": row.get("eps"),
        # V545: 年化 EPS 单独透出供前端展示（分红/估值按年计），保留原始 eps 供 PE 计算
        "eps_annualized": _annualize(_pct(row.get("eps")), row.get("report_date")),
        "bps": row.get("bps"),
        # V557: roe 还原为原始值（与 eps/revenue 一致），年化 ROE 走 roe_annualized
        "roe": row.get("roe"),
        # V530/V557: 年化 ROE 透出，与 score_tree 打分口径一致（一季报不再显示被低估的
        # 单季 ROE）；前端展示与分类「高ROE」判断不再矛盾
        "roe_annualized": _annualize(_pct(row.get("roe")), row.get("report_date")),
        "gross_margin": row.get("gross_margin"),
        "net_margin": row.get("net_margin"),
        "debt_ratio": row.get("debt_ratio"),
        "rev_yoy": row.get("rev_yoy"),
        "np_yoy": row.get("np_yoy"),
        "net_profit": row.get("net_profit"),
        # V558: 净利润同为年初至今累计值，年化单独透出（与 eps/revenue/roe 对称）
        "net_profit_annualized": _annualize(_pct(row.get("net_profit")), row.get("report_date")),
        "revenue": row.get("revenue"),
        # V551: 营收年化单独透出（与 eps_annualized 对称，一季报营收为累计值）
        "revenue_annualized": _annualize(_pct(row.get("revenue")), row.get("report_date")),
        "ocf": row.get("ocf"),
        "ocf_ps": row.get("ocf_ps"),
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
