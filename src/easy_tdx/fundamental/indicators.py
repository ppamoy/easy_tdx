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
import os
import re
import zipfile
from dataclasses import dataclass, field
from datetime import date
from datetime import datetime as dt_datetime
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


def _coerce_date(v: Any) -> date | None:
    """把 disclosure_date/report_date 归一化成 datetime.date，失败返回 None。

    V731：pick_report 的 point-in-time 比较要求两侧类型一致。外部传入的
    DataFrame 里日期可能是 date / str / pandas.Timestamp / datetime /
    NaT，直接 `dd <= target` 会在 str、Timestamp 上抛 TypeError（实测
    复现）。这里统一收敛到 date；无法解析的返回 None，由调用方按
    「无法判定 ⇒ 保守排除」处理，绝不把未知记录当成已披露。

    注意：datetime 是 date 的子类，这里也归一成 date，避免
    `datetime <= date` 在部分 pandas 版本上的比较歧义。
    """
    # NaT 检查必须放在 isinstance(date) **之前**：pd.NaT 同时是
    # datetime/date 的实例，若先按 date 命中就会原样返回 NaT，
    # 后续 `NaT <= target` 仍会抛 TypeError（实测复现）。
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(v, dt_datetime):
        return v.date()
    if isinstance(v, date):
        return v
    try:
        ts = pd.to_datetime(v, errors="coerce")
    except (TypeError, ValueError):
        return None
    if ts is None or pd.isna(ts):
        return None
    # V733 CI 收口：``ts.date()`` 在 pandas 的类型标注里是 Any，strict 模式下
    # 不能直接当 ``date | None`` 返回。上面的 isna 已排掉 NaT，这里按 (y, m, d)
    # 重建一个真正的 date —— 比起 type: ignore，同时也**顺带保证**返回值不可能是
    # NaT 之类的 Timestamp 退化对象。
    return date(int(ts.year), int(ts.month), int(ts.day))


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


_GPCW_CACHE = Path(os.environ.get("HOME") or os.path.expanduser("~")) / ".easy_tdx" / "gpcw_cache"


def _calc_client() -> TdxClient:
    """创建连接计算服务器（gpcw 财报数据源）的客户端。

    gpcw 文件只在 calc host 提供；用默认 TdxClient() 可能连到行情服务器
    而拿到 0 字节，因此显式绑定 calc host。
    """
    from easy_tdx.config import get_calc_hosts

    hosts = get_calc_hosts()
    host = hosts[0] if hosts else None
    return TdxClient(host=host) if host else TdxClient()


def _cached_zip(filename: str, client: TdxClient | None = None) -> bytes | None:
    """下载并缓存 gpcw zip。返回原始字节，失败返回 None。"""
    _GPCW_CACHE.mkdir(parents=True, exist_ok=True)
    cache_name = filename.replace("tdxfin/", "").replace("/", "_")
    cache_path = _GPCW_CACHE / cache_name
    if cache_path.is_file() and cache_path.stat().st_size > 0:
        return cache_path.read_bytes()
    try:
        if client is None:
            client = _calc_client()
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

    与前端 market.detectMarket / sina._build_paper_code 口径一致：
    北交所（43/83/87/92/93/4xx/8xx）→ BJ；沪市（6/9/5 开头，含 B 股 900）→ SH；
    其余 → SZ。V521 修复：旧实现漏判 9 开头（900 B股→SZ、920/930 北交所→SZ）。
    """
    if code.startswith(("43", "83", "87", "92", "93", "4", "8")):
        return "BJ"
    if code.startswith(("6", "9", "5")):
        return "SH"
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


def frame_for_zip(
    filename: str,
    client: TdxClient | None = None,
    *,
    use_cache: bool = True,
) -> pd.DataFrame:
    """解析一份 gpcw zip 为指标帧，优先读 SQLite 缓存（V89）。

    - 命中缓存（格式版本一致）直接读库返回；
    - 未命中则 ``records_from_zip`` + ``build_indicator_frame`` 后写库。
    """
    if use_cache:
        from easy_tdx.fundamental.cache import load_frame, store_frame

        cached = load_frame(filename)
        if cached is not None:
            return cached
        recs = records_from_zip(filename, client)
        frame = build_indicator_frame(recs) if recs else pd.DataFrame()
        if not frame.empty:
            try:
                store_frame(filename, frame)
            except Exception as e:  # noqa: BLE001
                logger.warning("gpcw 指标帧写缓存失败 %s: %s", filename, e)
        return frame
    recs = records_from_zip(filename, client)
    return build_indicator_frame(recs) if recs else pd.DataFrame()


def load_all_periods_frame(
    filenames: list[str],
    client: TdxClient | None = None,
    *,
    codes: set[str] | None = None,
    markets: set[str] | None = None,
    use_cache: bool = True,
) -> pd.DataFrame:
    """按报告期逐份加载指标帧并纵向拼接（每份走 SQLite 缓存），再过滤股票。

    等价于 ``load_all_periods`` + ``build_indicator_frame`` 的组合，但每份 zip
    只解析一次（之后走缓存），是全市场扫描/选股的高效加载路径。
    """
    frames = [frame_for_zip(fn, client, use_cache=use_cache) for fn in filenames]
    frames = [f for f in frames if f is not None and not f.empty]
    if not frames:
        return pd.DataFrame()
    frame = pd.concat(frames, ignore_index=True)
    if codes is not None:
        frame = frame[frame["code"].isin(codes)]
    if markets is not None:
        frame = frame[frame["market"].isin(markets)]
    return frame


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


def annualize_ytd(v: float | None, report_date: Any) -> float | None:
    """把年初至今累计值按报告期月数年化（EPS/ROE 等）。

    通达信专业财务的「基本每股收益」「净资产收益率」均为年初至今累计值：
    一季报只含 3 个月、中报 6 个月、三季报 9 个月、年报 12 个月。直接用
    一季报数值判「高ROE」/算 PE 会系统性低估/高估。

    年化系数：3 月(*4)、6 月(*2)、9 月(*4/3)、12 月(*1)；无法解析报告期
    按年报处理（不放大，避免过度外推）。

    V517: 抽取为共享纯函数，供 pipeline（PE 年化 V504）与 screener（ROE 年化
    V507）复用，消除两处重复实现。
    """
    if v is None:
        return None
    month: int | None = None
    if report_date is not None:
        try:
            month = pd.Timestamp(report_date).month
        except (ValueError, TypeError):
            month = None
    factor = 1.0
    if month is not None:
        factor = {3: 4.0, 6: 2.0, 9: 4.0 / 3.0, 12: 1.0}.get(month, 1.0)
    return float(v) * factor


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

    规则（杜绝未来函数）——V732 已与 :func:`pick_reports_bulk` 逐条对齐，并由
    tests/unit/test_fundamental_pit_bulk_equivalence.py 的穷举/随机等价测试锁定：
    1. 只考虑 disclosure_date ≤ target 的记录（披露日**真正缺失**时用 report_date
       近似，且要求 report_date 与 target 相差不超过 100 天）；
    2. **披露日有值但无法解析（如 "junk"）⇒ 保守排除**，绝不退回报告期近似 ——
       读不懂日期的记录无法证明其已在 target 公开，放行即引入未来数据（PIT
       生命线，见 docs/PRODUCT_REQUIREMENTS.md §5）；
    3. 排序取 (披露日, 报告期) 复合降序，同披露日取报告期更新的那期。
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
        # V731：与 pick_reports_bulk（向量化版）保持一致，先做类型归一化。
        # 该函数自称「规则与 pick_report 完全一致」，但只有它做了
        # pd.to_datetime。本函数原本直接用 `dd <= target` 比较，当调用方
        # 传入的 disclosure_date 是 str / pandas.Timestamp 时会抛
        # TypeError（实测复现）——生产路径（gpcw 的 _to_date、新浪适配器的
        # date、SQLite 缓存反序列化）都产出真 date 所以从未触发，但本函数是
        # 公开 API 且被 4 处生产代码直接调用，类型契约不该靠调用方自觉。
        # 归一化失败（NaT/None）时**保守排除**：宁可漏掉这条，也绝不能把
        # 无法判定的记录当成「已披露」而引入未来数据。
        dd_raw = row.get("disclosure_date")
        dd = _coerce_date(dd_raw)
        rd = _coerce_date(row.get("report_date"))
        if dd_raw is not None and dd is None:
            # 披露日**有值但无法解析**（NaT/非法字符串）：不能当作「无披露日」
            # 而退回报告期近似——那等于用一条我们读不懂日期的记录参与
            # point-in-time 判定，存在引入未来数据的风险。保守排除。
            continue
        if dd is not None:
            if dd <= target:
                usable.append(row)
        elif rd is not None and rd <= target and (target - rd).days <= 100:
            usable.append(row)
    if not usable:
        return None

    # V731 排序键修正：此前**只用披露日**排序，同一天披露多期时（实测 gpcw
    # 里 2025-12-31 与 2026-03-31 两期都在 2026-04-29 披露）顺序由
    # iterrows() 原始顺序决定 → 可能取到**较旧**的报告期，等于用过期财报
    # 选股（不是未来数据，但结果同样错）。且该顺序与向量化实现
    # pick_reports_bulk 的 groupby.first() 不一致 —— 实测 400 只里 94 只
    # （23.5%）两者结果分叉，说明两者都在"碰运气"。
    # 复合键：(披露日, 报告期) 降序 —— 同披露日取报告期更新的那期。
    def _pit_sort_key(r: pd.Series) -> tuple[date, date]:
        d = _coerce_date(r.get("disclosure_date"))
        p = _coerce_date(r.get("report_date"))
        return (d or date.min, p or date.min)

    usable.sort(key=_pit_sort_key, reverse=True)
    return usable[0]


def pick_reports_bulk(
    frame: pd.DataFrame,
    target: date,
    *,
    markets: set[str] | None = None,
) -> pd.DataFrame:
    """批量 Point-in-time：对整张指标帧一次筛出每只股票「截至 target 已披露的最新一期」。

    与 :func:`pick_report`（逐股版）**语义一致**，但向量化：全市场几千只股票
    一次完成截断与去重，替代逐股调用的 O(N²) 遍历。

    入选规则（与 pick_report 逐条对应）：
    1. 披露日已知（可解析）⇒ 披露日 ≤ target；
    2. 披露日**真正缺失**（pick_report 判定为 ``dd_raw is None``，即只有真 None）
       ⇒ 用报告期近似：报告期 ≤ target 且相差 ≤100 天；
    3. **PIT 保守排除（关键）**：披露日「有值但无法解析」（``"junk"`` / NaN /
       NaT / NA ⇒ 都是「有值」，但解析不出日期）⇒ 直接排除，**不**退回报告期
       近似。因为一条我们读不懂日期的记录无法证明其在 target 时已公开，若按
       「缺失」处理并放行，等于用未来数据回填 —— 违反本项目的 point-in-time
       生命线（见 docs/PRODUCT_REQUIREMENTS.md §5）。

    排序与 pick_report 的复合键 ``(披露日, 报告期)`` 降序一致：披露日缺失的行
    其披露日键为 NaT（等价于 pick_report 里的 ``date.min``，排序时垫底），因此
    **不做** ``dd.fillna(rd)`` / ``rd.fillna(dd)`` 交叉填充 —— 交叉填充会让
    两条不同规则入选的行互相借用对方的日期，排序结果分叉（实测：一行 dd 缺失
    rd=2024-03-31、另一行 dd=2024-03-01 rd=2024-01-31，逐股选后者，交叉填充
    的批量版选前者）。

    一致性由 tests/unit/test_fundamental_pit_bulk_equivalence.py 的穷举/随机
    等价测试锁定（不是靠 docstring 声称）。

    注意事项（性能）：日期归一化走 ``Series.map(_coerce_date)``（逐值 Python
    调用），比纯 ``pd.to_datetime`` 慢约 3 倍（实测 50 万行 754ms vs 265ms）。
    这是为**与 pick_report 逐值语义完全一致**付出的代价：pick_report 判定
    「缺失」用的是 ``dd_raw is not None``（只有**真 None** 算缺失，NaN/NaT/NA
    都算「有值但无法解析」⇒ 保守排除），这与 ``Series.isna()`` 不同。若改成
    纯向量化的 ``isna()``，NaN/NaT 披露日的行会被误判为缺失而退回报告期近似
    —— 实测复现该分歧。全市场规模（约 1.6 万行）下这档开销可接受。

    Args:
        frame: ``build_indicator_frame`` 输出（含 code/market/report_date/disclosure_date）。
        target: 目标历史日期。
        markets: 限定市场集合（None=全部）。

    Returns:
        与 frame 同构的 DataFrame，每只股票仅保留披露日最新的一期。
    """
    if frame is None or frame.empty:
        return pd.DataFrame()
    sub = frame
    if markets:
        sub = sub[sub["market"].isin(markets)]
    if sub.empty:
        return sub

    # 与 pick_report 共用同一个归一化函数，逐值语义才可能一致。
    # dd_present = pick_report 里的 `dd_raw is not None`（只有真 None 算缺失）。
    dd_present = sub["disclosure_date"].map(lambda v: v is not None)
    dd = sub["disclosure_date"].map(_coerce_date)  # None = 缺失或无法解析
    rd = sub["report_date"].map(_coerce_date)
    dd_ok = dd.map(lambda v: v is not None)
    rd_ok = rd.map(lambda v: v is not None)

    # 规则1：披露日已知且 ≤ target
    usable_dd = dd_ok & (dd <= target)
    # 规则2：披露日真正缺失(真 None) ⇒ 报告期近似，且相差 ≤100 天
    usable_rd = (
        (~dd_present)
        & rd_ok
        & (rd <= target)
        & (rd.map(lambda r: (target - r).days <= 100 if r is not None else False))
    )
    # 规则3（PIT 保守排除）：dd 有值但解析失败 ⇒ usable_dd/usable_rd 都不成立，
    # 自动出局，绝不退回报告期近似。
    usable = usable_dd | usable_rd
    sub = sub[usable]
    if sub.empty:
        return sub
    dd = dd[usable]
    rd = rd[usable]

    # 排序键：(披露日, 报告期) 降序 —— 同披露日取报告期更新的那期。
    # V731：此前只用披露日，同日披露多期时由 groupby.first() 取原顺序第一条
    # （不确定），与 pick_report 的 iterrows() 顺序分叉（实测 23.5% 不一致）。
    # V732 两处修正：
    #  (a) 去掉 fillna 交叉填充（见 docstring 第 4 段）—— 交叉填充会让两条
    #      按不同规则入选的行互相借用对方日期，排序结果分叉（实测复现）。
    #  (b) kind="mergesort"：稳定排序，(dd, rd) 完全相同时回退到原行序，与
    #      pick_report 的 Python 稳定 sort(reverse=True) 一致。
    # 键为 object 列的 date|None，None 在降序时排末尾 —— 正对应 pick_report
    # 排序键里的 ``d or date.min``。
    sub = sub.assign(_pit_dd=dd, _pit_rd=rd)
    sub = sub.sort_values(["_pit_dd", "_pit_rd"], ascending=False, kind="mergesort")
    # head(1) 而非 first()：first(skipna=True) 会**逐列**跳过 NaN，把后几行的
    # 字段填进第一行（实测：选中行 report_date=None 时会被下一行的值顶替），
    # 与 pick_report「整行原样返回」不一致。head(1) 是纯取行、无列级回填。
    out = sub.groupby(["code", "market"], as_index=False).head(1)
    out = out.reset_index(drop=True).drop(columns=["_pit_dd", "_pit_rd"])
    return out
