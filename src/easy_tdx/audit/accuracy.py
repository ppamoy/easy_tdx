"""模型准确性审计管道（V722，R2）。

回答三个问题，全部用真实数据、可复核明细、禁止合成值（伪造哨兵：
数据缺失输出 null + data_missing，绝不填充）。

1. **长盈选股准不准**——marks 树/粮/菜分类在多个历史季末基期的分层
   前瞻收益（+20/+60/+250 交易日），对比同期上证指数超额；
2. **缠论择时准不准**——抽样标的跑缠论分析，买卖点走统一台账
   （web/signal_ledger）算分类型前瞻命中率（与面板同口径）；
3. **图表与模型是否一致**——Web 图表异步取数路径（fetch_qfq_klines）
   与审计同步路径各取一次 K 线，末根 bar 时间戳/收盘价不一致计入
   mismatches。

数据路径：MAC 同步客户端（本机标准 TDX 主机不返回个股/指数数据，
见 2026-09-23 首跑日志）。取数失败逐标的计入 data_missing。

诚实性说明：长盈分类为 marks.trade_date 时点快照；历史基期评估沿用
该分类（存在分类时点偏差）。完全 point-in-time 的分类重跑请用
`easy-tdx changying-mark --date <历史日>` 后再审计。

报告落盘 ~/.easy_tdx/audit/accuracy_<date>.json + .md。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

MAX_MARKS_AGE_DAYS = 35
AUDIT_HORIZONS: tuple[int, ...] = (20, 60, 250)
# 长盈前瞻收益的历史基期个数（季末），保证 250 日窗口有足够后向数据
BASE_COUNT = 5
_MIN_CLASS_SAMPLE = 30


def _audit_dir() -> Path:
    d = Path(os.environ.get("EASY_TDX_CONFIG_DIR", str(Path.home() / ".easy_tdx"))) / "audit"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def recent_quarter_ends(n: int = BASE_COUNT, today: date | None = None) -> list[date]:
    """最近 n 个已过去的季末日期（降序），作为长盈前瞻收益基期。"""
    today = today or date.today()
    ends: list[date] = []
    y, q = today.year, (today.month - 1) // 3  # 当前季度序号 0-3
    while len(ends) < n:
        q -= 1
        if q < 0:
            q = 3
            y -= 1
        month = q * 3 + 3
        day = {3: 31, 6: 30, 9: 30, 12: 31}[month]
        end = date(y, month, day)
        if end < today:
            ends.append(end)
    return ends


class MacSession:
    """审计期间复用一条 MAC 连接（同步客户端，与 CLI 数据路径一致）。"""

    def __init__(self) -> None:
        self.client: Any = None

    def __enter__(self) -> MacSession:
        from easy_tdx.mac.client import MacClient

        c = MacClient()
        c.connect()
        self.client = c
        return self

    def __exit__(self, *exc: Any) -> None:
        if self.client is not None:
            try:
                self.client.close()
            except Exception:  # noqa: BLE001
                pass
        self.client = None

    def kline(self, market: str, code: str, count: int = 800) -> pd.DataFrame:
        """个股 QFQ 日线；失败抛异常由调用方记 data_missing。"""
        from easy_tdx.mac.enums import Adjust, Period
        from easy_tdx.models.enums import Market

        df = self.client.get_stock_kline(
            int(Market[market.upper()].value),
            code,
            Period.DAILY,
            start=0,
            count=count,
            adjust=Adjust.QFQ,
        )
        if df is None or df.empty:
            raise ValueError("MAC 返回空 K 线")
        return df

    def index_kline(self, count: int = 1200) -> pd.DataFrame:
        """上证指数日线（不复权）。"""
        from easy_tdx.mac.enums import Adjust, Period

        df = self.client.get_stock_kline(
            1, "000001", Period.DAILY, start=0, count=count, adjust=Adjust.NONE
        )
        if df is None or df.empty:
            raise ValueError("MAC 返回空指数 K 线")
        return df


def _returns_at_dates(
    df: pd.DataFrame,
    bases: list[date],
    horizons: tuple[int, ...],
) -> dict[str, dict[str, Any]]:
    """给定日线 DataFrame，对每个基期算 N 交易日前瞻收益。

    Returns: {"<base_iso>": {"ret_20d": float|None, ..., "bars_after": int}}
    前瞻 bar 不足时该窗口为 null（诚实缺失，不外推）。
    """
    col = "date" if "date" in df.columns else "datetime"
    dates = pd.to_datetime(df[col]).dt.date
    closes = df["close"].astype(float).tolist()
    out: dict[str, dict[str, Any]] = {}
    for b in bases:
        idx = next((i for i, d in enumerate(dates) if d >= b), None)
        if idx is None:
            out[str(b)] = {"error": "基期晚于最后 bar", "bars_after": 0}
            continue
        base = closes[idx]
        entry: dict[str, Any] = {
            "as_of_close": round(base, 2),
            "bars_after": len(closes) - idx - 1,
        }
        if idx == 0 and dates[0] > b:
            # 诚实标记：基期早于上市，回退到上市首日为基期
            entry["base_clamped_to_listing"] = True
        for h in horizons:
            j = idx + h
            if j < len(closes) and base:
                entry[f"ret_{h}d"] = round((closes[j] / base - 1) * 100, 2)
            else:
                entry[f"ret_{h}d"] = None
        out[str(b)] = entry
    return out


# ── 1. 长盈分层前瞻收益 ──────────────────────────────────────────────────


def _sample_marks(samples: int, seed: int) -> dict[str, list[dict[str, Any]]]:
    """按分类确定性抽样（seed 固定保证审计可复现）。"""
    from easy_tdx.fundamental.marks import ChangyingMarkStore

    marks = ChangyingMarkStore().load_marks()
    if not marks:
        return {}
    by_cat: dict[str, list[dict[str, Any]]] = {}
    for r in marks["results"]:
        by_cat.setdefault(r["category"], []).append(r)
    rng = random.Random(seed)
    out: dict[str, list[dict[str, Any]]] = {}
    for cat, rows in by_cat.items():
        n = min(samples, len(rows))
        out[cat] = (
            sorted(rows, key=lambda r: r["symbol"])[:n]
            if len(rows) <= samples
            else rng.sample(rows, n)
        )
    return out


def audit_changying(
    bases: list[date],
    samples: int,
    seed: int = 42,
    session: MacSession | None = None,
) -> dict[str, Any]:
    """长盈分层前瞻收益审计（真实行情，缺失留 null）。"""
    sampled = _sample_marks(samples, seed)
    if not sampled:
        return {
            "error": "marks 表为空，请先运行 easy-tdx changying-mark",
            "data_missing": True,
        }

    own = session is None
    if own:
        session = MacSession()
        session.__enter__()
    assert session is not None  # own 分支已构造；外部传入由调用方保证
    try:
        try:
            idx_df = session.index_kline()
            index_perf = _returns_at_dates(idx_df, bases, AUDIT_HORIZONS)
        except Exception as e:  # noqa: BLE001
            logger.warning("审计取指数失败: %s", e)
            index_perf = {}

        per_symbol: list[dict[str, Any]] = []
        per_class: dict[str, dict[str, Any]] = {}
        for cat, rows in sorted(sampled.items()):
            stats_rows: list[dict[str, Any]] = []
            for r in rows:
                entry: dict[str, Any] = {
                    "symbol": r["symbol"],
                    "category": cat,
                    "score": r.get("score"),
                    "report_date": r.get("report_date"),
                    "data_missing": False,
                }
                try:
                    df = session.kline(r["market"], r["code"], count=1200)
                    perf = _returns_at_dates(df, bases, AUDIT_HORIZONS)
                except Exception as e:  # noqa: BLE001
                    entry["data_missing"] = True
                    entry["error"] = str(e)[:120]
                    perf = {}
                entry["performance"] = perf
                # point-in-time 哨兵：财报期必须早于 marks 快照日
                rd = r.get("report_date")
                entry["pit_ok"] = bool(rd and str(rd) <= str(r.get("trade_date") or date.today()))
                per_symbol.append(entry)
                stats_rows.append(entry)
            cls_stats: dict[str, Any] = {"samples": len(stats_rows)}
            for b in bases:
                bk = str(b)
                slot: dict[str, Any] = {}
                for h in AUDIT_HORIZONS:
                    rets: list[float] = []
                    excs: list[float] = []
                    for row_e in stats_rows:
                        p = (row_e.get("performance") or {}).get(bk) or {}
                        v = p.get(f"ret_{h}d")
                        if v is not None:
                            rets.append(float(v))
                            iv = (index_perf.get(bk) or {}).get(f"ret_{h}d")
                            if iv is not None:
                                excs.append(float(v) - float(iv))
                    slot[f"ret_{h}d"] = {
                        "n": len(rets),
                        "p50": round(float(np.percentile(rets, 50)), 2) if rets else None,
                        "win_rate": (
                            round(sum(1 for v in rets if v > 0) / len(rets), 4) if rets else None
                        ),
                    }
                    slot[f"excess_{h}d"] = {
                        "n": len(excs),
                        "p50": round(float(np.percentile(excs, 50)), 2) if excs else None,
                        "win_rate": (
                            round(sum(1 for v in excs if v > 0) / len(excs), 4) if excs else None
                        ),
                    }
                cls_stats[bk] = slot
            cls_stats["pit_violations"] = sum(1 for e in stats_rows if not e["pit_ok"])
            cls_stats["data_missing"] = sum(1 for e in stats_rows if e["data_missing"])
            per_class[cat] = cls_stats
        return {
            "bases": [str(b) for b in bases],
            "index": index_perf,
            "per_class": per_class,
            "per_symbol": per_symbol,
            "caveat": "分类为 marks.trade_date 时点快照；"
            "完全 point-in-time 重跑用 changying-mark --date",
        }
    finally:
        if own:
            session.__exit__(None, None, None)


# ── 2. 缠论买卖点信号质量 ────────────────────────────────────────────────


def _flat_sample(
    symbols: dict[str, list[dict[str, Any]]], limit: int, seed: int
) -> list[dict[str, Any]]:
    """分类抽样摊平并限量（缠论分析逐只要跑，控制耗时）。"""
    rng = random.Random(seed + 1)
    pool = [r for rows in symbols.values() for r in rows]
    if len(pool) <= limit:
        return pool
    return rng.sample(pool, limit)


def audit_chanlun(
    samples: int,
    chanlun_limit: int = 15,
    seed: int = 42,
    session: MacSession | None = None,
) -> dict[str, Any]:
    """缠论买卖点分类型命中率审计（与 signal_quality 面板同口径）。

    汇总各类型信号的方向对齐前瞻收益（signal_ledger 统一台账），
    按类型输出命中率与平均收益；窗口 (5, 20) 根。
    """
    from easy_tdx.chanlun import ChanlunAnalyser, ChanlunConfig
    from easy_tdx.web.signal_ledger import signal_returns

    sampled = _sample_marks(samples, seed)
    if not sampled:
        return {"error": "无可用抽样标的", "data_missing": True}
    chosen = _flat_sample(sampled, chanlun_limit, seed)

    own = session is None
    if own:
        session = MacSession()
        session.__enter__()
    assert session is not None  # own 分支已构造；外部传入由调用方保证
    try:
        per_type: dict[str, dict[str, Any]] = {}
        per_symbol: list[dict[str, Any]] = []
        total_signals = 0
        for r in chosen:
            try:
                df = session.kline(r["market"], r["code"], count=800)
            except Exception as e:  # noqa: BLE001
                per_symbol.append(
                    {"symbol": r["symbol"], "data_missing": True, "error": str(e)[:120]}
                )
                continue
            analyser = ChanlunAnalyser(
                code=f"{r['market']}{r['code']}",
                frequency="daily",
                config=ChanlunConfig(),
            )
            try:
                result = analyser.process_klines(df)
            except Exception as e:  # noqa: BLE001
                per_symbol.append({"symbol": r["symbol"], "error": f"chanlun: {e}"[:120]})
                continue
            closes = [float(k.close) for k in result.klines]
            sigs = [
                {"type": m.mmd_type.value, "bar_index": m.bi.end.bar_index if m.bi else None}
                for m in result.mmds
            ]
            recs = signal_returns(closes, sigs, horizons=(5, 20))
            total_signals += len(sigs)
            per_symbol.append({"symbol": r["symbol"], "bars": len(df), "signals": len(sigs)})
            for rec in recs:
                if rec.ret_pct is None:
                    continue
                slot = per_type.setdefault(rec.signal_type, {"rets": [], "hits": 0, "n": 0})
                slot["rets"].append(float(rec.ret_pct))
                slot["n"] += 1
                if rec.ret_pct > 0:
                    slot["hits"] += 1
        by_type: dict[str, Any] = {}
        for t, slot in sorted(per_type.items()):
            by_type[t] = {
                "signals": slot["n"],
                "hit_rate": round(slot["hits"] / slot["n"], 4) if slot["n"] else None,
                "avg_return": round(float(np.mean(slot["rets"])), 4) if slot["rets"] else None,
            }
        return {
            "note": "口径：信号后 N 根收盘对收盘（signal_ledger 统一台账，方向对齐，与面板一致）",
            "sample_size": len(chosen),
            "signal_count": total_signals,
            "by_type": by_type,
            "per_symbol": per_symbol,
        }
    finally:
        if own:
            session.__exit__(None, None, None)


# ── 3. 图表对账 ──────────────────────────────────────────────────────────


def audit_chart_consistency(samples: int = 8, seed: int = 42) -> dict[str, Any]:
    """图表异步路径 vs 审计同步路径：末根 bar 时间戳与收盘价必须一致。

    图表侧用 Web 同款 AsyncMacClient + fetch_qfq_klines（QFQ），
    审计侧用同步 MacSession.kline（同 QFQ）。两路不一致说明图表
    展示的价格体系与模型计算脱节——正是用户要抓的那类问题。
    """
    from easy_tdx.fundamental.marks import ChangyingMarkStore

    marks = ChangyingMarkStore().load_marks(top_n=50)
    if not marks:
        return {"checked": 0, "mismatches": [], "error": "marks 为空"}
    rng = random.Random(seed + 2)
    pool = marks["results"]
    chosen = pool if len(pool) <= samples else rng.sample(pool, samples)

    mismatches: list[dict[str, Any]] = []
    checked = 0

    async def _chart_last(market: str, code: str) -> dict[str, Any]:
        from easy_tdx.mac.client import AsyncMacClient
        from easy_tdx.web.klines import fetch_qfq_klines

        mac = AsyncMacClient.from_best_host()
        await mac.connect()
        try:
            df = await fetch_qfq_klines(mac, None, market, code, "DAY", 0, 800)
        finally:
            try:
                await mac.close()
            except Exception:  # noqa: BLE001
                pass
        if df is None or df.empty:
            raise ValueError("图表路径空 K 线")
        col = "date" if "date" in df.columns else "datetime"
        return {"last": str(df[col].iloc[-1])[:10], "close": float(df["close"].iloc[-1])}

    with MacSession() as session:
        loop = asyncio.new_event_loop()
        try:
            for r in chosen:
                try:
                    chart = loop.run_until_complete(_chart_last(r["market"], r["code"]))
                    df = session.kline(r["market"], r["code"], count=800)
                    col = "date" if "date" in df.columns else "datetime"
                    audit = {
                        "last": str(df[col].iloc[-1])[:10],
                        "close": float(df["close"].iloc[-1]),
                    }
                except Exception as e:  # noqa: BLE001
                    mismatches.append({"symbol": r["symbol"], "error": str(e)[:120]})
                    continue
                checked += 1
                if chart["last"] != audit["last"] or abs(chart["close"] - audit["close"]) > 1e-6:
                    mismatches.append({"symbol": r["symbol"], "chart": chart, "audit": audit})
        finally:
            loop.close()
    return {"checked": checked, "mismatches": mismatches}


# ── 报告组装与落盘 ────────────────────────────────────────────────────────


def run_accuracy_audit(
    *,
    samples: int = _MIN_CLASS_SAMPLE,
    chanlun_limit: int = 15,
    seed: int = 42,
    skip_chanlun: bool = False,
) -> dict[str, Any]:
    """跑完整审计并落盘 JSON/Markdown，返回报告 dict。"""
    from easy_tdx.fundamental.marks import ChangyingMarkStore

    bases = recent_quarter_ends()
    meta = ChangyingMarkStore().last_snapshot_meta() or {}
    marks_age_days = None
    if meta.get("updated_at"):
        marks_age_days = (
            datetime.now(timezone.utc) - datetime.fromisoformat(meta["updated_at"])
        ).days

    report: dict[str, Any] = {
        "generated_at": _now_iso(),
        "bases": [str(b) for b in bases],
        "marks": {
            "count": meta.get("count"),
            "trade_date": meta.get("trade_date"),
            "by_category": meta.get("by_category"),
            "age_days": marks_age_days,
            "stale": marks_age_days is None or marks_age_days > MAX_MARKS_AGE_DAYS,
        },
    }
    with MacSession() as session:
        report["changying"] = audit_changying(bases, samples, seed, session)
        if not skip_chanlun:
            try:
                report["chanlun"] = audit_chanlun(samples, chanlun_limit, seed, session)
            except Exception as e:  # noqa: BLE001
                logger.exception("缠论审计失败")
                report["chanlun"] = {"error": str(e), "data_missing": True}
        else:
            report["chanlun"] = {"skipped": True}
    try:
        report["chart_consistency"] = audit_chart_consistency(seed=seed)
    except Exception as e:  # noqa: BLE001
        logger.exception("图表对账失败")
        report["chart_consistency"] = {"error": str(e)}

    d = _audit_dir()
    target_iso = date.today().isoformat()
    json_path = d / f"accuracy_{target_iso}.json"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    md_path = d / f"accuracy_{target_iso}.md"
    md_path.write_text(render_markdown(report), encoding="utf-8")
    report["files"] = {"json": str(json_path), "markdown": str(md_path)}
    (d / "latest.json").write_text(
        json.dumps({"date": target_iso, "json": str(json_path)}, ensure_ascii=False),
        encoding="utf-8",
    )
    return report


def load_latest_audit() -> dict[str, Any] | None:
    """读取最新审计报告（Web 消费），无报告返回 None。"""
    d = _audit_dir()
    latest = d / "latest.json"
    if not latest.exists():
        return None
    try:
        ptr = json.loads(latest.read_text(encoding="utf-8"))
        loaded: dict[str, Any] = json.loads(Path(ptr["json"]).read_text(encoding="utf-8"))
        return loaded
    except (OSError, ValueError, KeyError):
        return None


def list_audit_history() -> list[dict[str, Any]]:
    """历史报告列表（日期 + 路径），按日期降序。"""
    return [
        {"date": p.stem.replace("accuracy_", ""), "path": str(p)}
        for p in sorted(_audit_dir().glob("accuracy_*.json"), reverse=True)
    ]


def render_markdown(report: dict[str, Any]) -> str:
    """审计报告 → Markdown（Web 页与人工阅读共用）。"""
    lines: list[str] = ["# 长盈 + 缠论 准确性审计报告", ""]
    lines.append(f"- 生成时间：{report.get('generated_at')}")
    lines.append(f"- 前瞻基期：{', '.join(report.get('bases', []))}")
    marks = report.get("marks") or {}
    stale = "⚠️ **已过期**" if marks.get("stale") else "正常"
    lines.append(f"- marks 快照：{marks.get('count')} 只（{marks.get('trade_date')}，{stale}）")
    lines.append("")

    cy = report.get("changying") or {}
    if cy.get("data_missing"):
        lines.append(f"> ⚠️ 长盈审计：{cy.get('error', '数据缺失')}")
    else:
        lines.append("## 长盈分层前瞻收益（中位数% / 胜率）")
        bases = cy.get("bases", [])
        for h in AUDIT_HORIZONS:
            lines.append("")
            lines.append(f"### +{h} 交易日")
            lines.append("")
            head = "| 分类 | " + " | ".join(bases) + " | 超额胜率(最新基期) | PIT 违规 |"
            sep = "| --- | " + " | ".join("---" for _ in bases) + " | --- | --- |"
            lines.append(head)
            lines.append(sep)
            for cat, s in (cy.get("per_class") or {}).items():
                cells = []
                for b in bases:
                    slot = (s.get(b) or {}).get(f"ret_{h}d") or {}
                    cells.append(f"{slot.get('p50')} / {slot.get('win_rate')}")
                first = (s.get(bases[0]) or {}).get(f"excess_{h}d") or {} if bases else {}
                lines.append(
                    f"| {cat} | "
                    + " | ".join(cells)
                    + f" | {first.get('win_rate')} | {s.get('pit_violations')} |"
                )
        lines.append("")
        lines.append(f"> {cy.get('caveat')}")
        lines.append("")

    cl = report.get("chanlun") or {}
    if cl.get("skipped"):
        lines.append("## 缠论信号质量（本次跳过）")
    elif cl.get("data_missing"):
        lines.append(f"> ⚠️ 缠论审计：{cl.get('error', '数据缺失')}")
    else:
        lines.append("## 缠论买卖点信号质量")
        lines.append("")
        lines.append(
            f"样本 {cl.get('sample_size')} 只，有效信号 {cl.get('signal_count')} 条。"
            f"{cl.get('note')}"
        )
        lines.append("")
        lines.append("| 类型 | 有效信号 | 命中率(5根) | 平均收益%(5根) |")
        lines.append("| --- | --- | --- | --- |")
        for t, s in (cl.get("by_type") or {}).items():
            lines.append(
                f"| {t} | {s.get('signals')} | {s.get('hit_rate')} | {s.get('avg_return')} |"
            )
        lines.append("")

    cc = report.get("chart_consistency") or {}
    if cc:
        mm = cc.get("mismatches") or []
        badge = "❌ 存在不一致" if mm else "✅ 一致"
        lines.append("")
        lines.append(f"## 图表对账（{cc.get('checked', 0)} 只抽样）：{badge}")
        for m in mm:
            lines.append(f"- {m}")
        lines.append("")
    return "\n".join(lines) + "\n"
