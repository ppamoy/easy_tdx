"""P1 长赢基本面选股 —— 财务指标层（gpcw 历史财报 → 指标 + 披露日 point-in-time）。

数据源：通达信专业财务 gpcw*.zip（``TdxClient.get_financial_records``），
字段顺序见 :mod:`easy_tdx.fundamental.gpcw_fields`。

核心职责：

1. 拉取/缓存指定报告期的全市场财务记录，映射为具名字段；
2. 把单只股票的多期记录整理为时间序列，并计算派生指标
   （毛利率、净利率、营收/净利同比、ROE、负债率、经营现金流等）；
3. 按披露日（财报公告日期）做 point-in-time 截断：只返回
   「截至目标日期 T 已披露」的最新年报/季报，杜绝未来函数。
"""

from __future__ import annotations

import io
import logging
import re
import zipfile
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from easy_tdx.client import TdxClient
from easy_tdx.codec.financial import parse_financial_dat
from easy_tdx.fundamental.gpcw_fields import GPCW_FIELDS, F

logger = logging.getLogger(__name__)

# ── 报告期文件名 → 报告期（YYYYMMDD int） ────────────────────────────────
_PERIOD_RE = re.compile(r"(\d{8})")


def _period_from_filename(filename: str) -> int:
    m = _PERIOD_RE.search(filename)
    return int(m.group(1)) if m else 0



def _to_date(v: Any) -> date | None:
    """gpcw 公告日期字段（float，YYMMDD 或 YYYYMMDD）→ date。0/NaN 返回 None。"""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if not f or f <= 0:
        return None
    s = str(int(f))
    try:
        if len(s) == 8 and s[:2] in ("19", "20"):
            y, mm, dd = int(s[:4]), int(s[4:6]), int(s[6:8])
        elif len(s) == 6:
            y = 2000 + int(s[:2])
            mm, dd = int(s[2:4]), int(s[4:6])
        else:
            return None
        return date(y, mm, dd)
    except ValueError:
        return None


def _dt(v: Any) -> date | None:
    """报告期 int YYYYMMDD → date。"""
    if not v:
        return None
    s = str(int(v)).zfill(8)
    try:
        return date(int(s[:4]), int(s[4:6]), int(s[6:8]))
    except ValueError:
        return None


def _f(v: Any) -> float | None:
    """float 转换，NaN/0 不变（0 可能是“无数据”也可能是真实 0）。"""
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


_GPCW_CACHE = Path.home() / ".easy_tdx" / "gpcw_cache"



def _cached_zip(filename: str, client: TdxClient | None = None) -> bytes | None:
    """下载并缓存 gpcw zip。返回原始字节，失败返回 None。"""
    _GPCW_CACHE.mkdir(parents=True, exist_ok=True)
    cache_name = filename.replace("tdxfin/", "").replace("/", "_")
    cache_path = _GPCW_CACHE / cache_name
    if cache_path.is_file() and cache_path.stat().st_size > 0:
        return cache_path.read_bytes()
    try:
        if client is None:
            client = TdxClient()
        data = client.get_financial_file(filename)
    except Exception as e:  # noqa: BLE001
        logger.warning("gpcw 下载失败 %s: %s", filename, e)
        return None
    if not data:
        return None
    cache_path.write_bytes(data)
    return data


@dataclass
class ReportRecord:
    """一只股票一个报告期的一条财报记录（具名字段）。"""

    code: str
    market: str
    report_date: date | None
    disclosure_date: date | None
    values: dict[str, float | None] = field(default_factory=dict)

    def get(self, name: str) -> float | None:
        return self.values.get(name)

    def ratio(self, num: str, den: str) -> float | None:
        a = self.get(num)
        b = self.get(den)
        if a is None or not b:
            return None
        return a / b



def _market_from_code(code: str) -> str:
    """按 A 股代码前缀推断市场（gpcw 索引里的 market 字节不可靠，经常全 0）。

    6xxxxx → SH；4/8xxxxx(43x/83x/87x/92x 等) → BJ；其余(SZ) 默认。
    """
    if code.startswith("6"):
        return "SH"
    if code.startswith(("4", "8")):
        return "BJ"
    return "SZ"


def records_from_zip(filename: str, client: TdxClient | None = None) -> list[ReportRecord]:
    """解析一个 gpcw zip 为具名财报记录列表（全市场）。"""
    data = _cached_zip(filename, client)
    if not data:
        return []
    report_date = _period_from_filename(filename)  # noqa: F841
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            dat_names = [n for n in zf.namelist() if n.endswith(".dat")]
            if not dat_names:
                return []
            dat = zf.read(dat_names[0])
    except (zipfile.BadZipFile, KeyError) as e:
        logger.warning("解析 gpcw zip %s 失败: %s", filename, e)
        return []
    raw = parse_financial_dat(dat, report_date)
    out: list[ReportRecord] = []
    for code, market_byte, rdate, fields in raw:
        market = _market_from_code(code)
        values: dict[str, float | None] = {}
        for i, name in enumerate(GPCW_FIELDS):
            values[name] = _f(fields[i]) if i < len(fields) else None
        rec = ReportRecord(
            code=code,
            market=market,
            report_date=_dt(rdate),
            disclosure_date=_to_date(
                values.get(GPCW_FIELDS[F.DATE_REPORT]) if F.DATE_REPORT >= 0 else None
            ),
            values=values,
        )
        # 字段越界保护
        del values
        out.append(rec)
    return out


def load_all_periods(
    filenames: list[str],
    client: TdxClient | None = None,
    *,
    codes: set[str] | None = None,
    markets: set[str] | None = None,
) -> list[ReportRecord]:
    """加载多个报告期的财报记录，只保留目标股票。

    Args:
        filenames: gpcw 文件名列表（报告期倒序/正序均可，会按报告期排序）。
        codes: 只保留这些 6 位代码（None=全部）。
        markets: 只保留这些市场（SZ/SH）。
    """
    result: list[ReportRecord] = []
    for fn in filenames:
        recs = records_from_zip(fn, client)
        for rec in recs:
            if codes is not None and rec.code not in codes:
                continue
            if markets is not None and rec.market not in markets:
                continue
            result.append(rec)
    # 按 (code, report_date) 排序
    result.sort(key=lambda r: (r.code, r.report_date or date.min))
    return result


def build_indicator_frame(
    records: list[ReportRecord],
    *,
    include_raw: bool = False,
) -> pd.DataFrame:
    """把 ReportRecord 列表展平为 DataFrame（每行 = 一只股票一个报告期）。

    列：code / market / report_date / disclosure_date / 派生指标。
    """
    rows: list[dict[str, Any]] = []
    for r in records:
        row: dict[str, Any] = {
            "code": r.code,
            "market": r.market,
            "report_date": r.report_date,
            "disclosure_date": r.disclosure_date,
        }
        v = r.values
        row.update(indicator_values(v))
        if include_raw:
            row["raw"] = v
        rows.append(row)
    return pd.DataFrame(rows)


def indicator_values(v: dict[str, float | None]) -> dict[str, Any]:
    """从原始字段 dict 计算派生指标集。

    gpcw 的同比字段是「%」数值（如 18.30 = +18.3%），比率字段（ROE/毛利率等）
    同样是百分数（如 33.65 = 33.65%）。派生命中统一保留百分数含义，
    前端展示时加 “%”。
    """
    g = v.get
    rev = g("其中：营业收入")
    cogs = g("其中：营业成本")
    np = g("归属于母公司所有者的净利润")
    assets = g("资产总计")
    liab = g("负债合计")
    ocf = g("经营活动产生的现金流量净额")
    eps = g("基本每股收益")
    bps = g("每股净资产")
    roe = g("净资产收益率")
    gross = None
    if rev is not None and cogs is not None and rev:
        gross = (rev - cogs) / rev * 100.0
    net_margin = None
    if rev is not None and np is not None and rev:
        net_margin = np / rev * 100.0
    debt_ratio = None
    if assets is not None and liab is not None and assets:
        debt_ratio = liab / assets * 100.0
    return {
        "eps": eps,
        "bps": bps,
        "roe": roe,
        "revenue": rev,
        "net_profit": np,
        "gross_margin": gross,
        "net_margin": net_margin,
        "debt_ratio": debt_ratio,
        "ocf": ocf,
        "ocf_ps": g("每股经营现金流量"),
        "rev_yoy": g("营业收入增长率(%)"),
        "np_yoy": g("净利润增长率(%)"),
        "asset_yoy": g("总资产增长率(%)"),
        "op_yoy": g("营业利润增长率(%)"),
        "total_shares": g("总股本"),
        "circ_a": g("已上市流通A股"),
    }


def pick_report(
    frame: pd.DataFrame,
    code: str,
    target: date,
    *,
    market: str | None = None,
) -> pd.Series | None:
    """Point-in-time：从某只股票的多期记录中挑出「截至 target 已披露的最新一期」。

    规则（杜绝未来函数）：
    1. 只考虑 disclosure_date ≤ target 的记录（缺失披露日的用 report_date 近似，
       且要求 report_date 与 target 相差不超过 100 天，避免用未披露数据）；
    2. 同报告期优先选披露日确定的那条；
    3. 返回披露日最新的一期。
    """
    sub = frame[frame["code"] == code]
    if sub.empty:
        return None
    if market:
        m = sub[sub["market"] == market]
        if not m.empty:
            sub = m
    usable: list[pd.Series] = []
    for _, row in sub.iterrows():
        dd = row.get("disclosure_date")
        rd = row.get("report_date")
        if dd is not None:
            if dd <= target:
                usable.append(row)
        elif rd is not None and rd <= target and (target - rd).days <= 100:
            usable.append(row)
    if not usable:
        return None
    usable.sort(key=lambda r: (r["disclosure_date"] or r["report_date"] or date.min), reverse=True)
    return usable[0]
