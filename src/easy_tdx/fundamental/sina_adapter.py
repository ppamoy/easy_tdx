"""新浪财报数据源适配器：用于 gpcw 未覆盖（或下载受限）的历史时点。

新浪财报接口返回利润表/资产负债表/现金流量表，按报告期组织（最新在前）。
本模块把三表合并成与 gpcw 一致的财务指标（indicators.py 的派生指标口径），
并用「披露日估算」支持 point-in-time 截断（年报 4/30、一季报 4/30、中报 8/31、三季报 10/31）。

用法：在 load_pool 里作为 gpcw 的补充数据源，覆盖更早历史时点。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class SinaFinancialRow:
    """一只股票一个报告期的合并指标（口径与 gpcw 派生指标一致）。"""

    code: str
    market: str
    report_date: date | None
    disclosure_date: date | None
    indicators: dict[str, Any]


def _disclosure_estimate(report_date: date | None) -> date | None:
    """估算报告期的披露日（监管截止口径，保守取截止日）。

    - 年报 12-31 → 次年 4-30
    - 一季报 03-31 → 当年 4-30
    - 中报 06-30 → 当年 8-31
    - 三季报 09-30 → 当年 10-31
    """
    if report_date is None:
        return None
    y, m, d = report_date.year, report_date.month, report_date.day
    if (m, d) == (12, 31):
        return date(y + 1, 4, 30)
    if (m, d) == (3, 31):
        return date(y, 4, 30)
    if (m, d) == (6, 30):
        return date(y, 8, 31)
    if (m, d) == (9, 30):
        return date(y, 10, 31)
    return report_date


def _pct_ratio(v: Any, base: Any) -> float | None:
    if v is None or not base:
        return None
    try:
        return v / base * 100.0
    except (TypeError, ValueError):
        return None


def _yoy_pct(v: Any) -> float | None:
    """新浪同比为小数（0.0634=+6.34%），转百分数。"""
    if v is None:
        return None
    try:
        return float(v) * 100.0
    except (TypeError, ValueError):
        return None


def load_sina_rows(code: str, market: str = "SZ", num: int = 40) -> list[SinaFinancialRow]:
    """拉取一只股票最近 N 期财报并合并为指标行（最新在前）。

    Args:
        code: 6 位股票代码。
        market: SH / SZ（用于点选市场标签）。
        num: 报告期数。
    """
    from easy_tdx.sina.client import SinaClient

    client = SinaClient(timeout=40)
    lrb = client.get_financial_report(code, "lrb", num=num)
    fzb = client.get_financial_report(code, "fzb", num=num)
    llb = client.get_financial_report(code, "llb", num=num)

    if lrb is None or lrb.empty:
        return []

    rows: list[SinaFinancialRow] = []
    for _, row in lrb.iterrows():
        period = row.get("报告期")
        if period is None:
            continue
        try:
            rdate = pd.to_datetime(period).date()
        except Exception:
            rdate = None

        def _fzb(col: str):
            if fzb is None or fzb.empty:
                return None
            sub = fzb[fzb["报告期"].astype(str) == str(period)]
            if sub.empty or col not in sub.columns:
                return None
            v = sub.iloc[0][col]
            return None if pd.isna(v) else float(v)

        def _llb(col: str):
            if llb is None or llb.empty:
                return None
            sub = llb[llb["报告期"].astype(str) == str(period)]
            if sub.empty or col not in sub.columns:
                return None
            v = sub.iloc[0][col]
            return None if pd.isna(v) else float(v)

        rev = row.get("营业总收入")
        np_parent = row.get("归属于母公司所有者的净利润")
        eps = row.get("基本每股收益")
        equity = _fzb("所有者权益(或股东权益)合计")
        assets = _fzb("资产总计")
        liab = _fzb("负债合计")
        ocf = _llb("经营活动产生的现金流量净额")

        def _num(x: Any) -> float | None:
            if x is None or pd.isna(x):
                return None
            try:
                return float(x)
            except (TypeError, ValueError):
                return None

        rev = _num(rev)
        np_parent = _num(np_parent)
        eps = _num(eps)
        equity = _num(equity)
        assets = _num(assets)
        liab = _num(liab)
        ocf = _num(ocf)

        gross = None
        cogs = _num(row.get("营业成本")) if "营业成本" in row else None
        if rev is not None and cogs is not None and rev:
            gross = (rev - cogs) / rev * 100.0

        ind = {
            "eps": eps,
            "roe": _pct_ratio(np_parent, equity),
            "revenue": rev,
            "net_profit": np_parent,
            "gross_margin": gross,
            "net_margin": _pct_ratio(np_parent, rev),
            "debt_ratio": _pct_ratio(liab, assets),
            "ocf": ocf,
            "rev_yoy": _yoy_pct(row.get("营业总收入_同比")),
            "np_yoy": _yoy_pct(row.get("归属于母公司所有者的净利润_同比")),
        }
        rows.append(
            SinaFinancialRow(
                code=code,
                market=market,
                report_date=rdate,
                disclosure_date=_disclosure_estimate(rdate),
                indicators=ind,
            )
        )
    return rows
