"""长盈选股池离线刷新命令（凌晨 cron 用）。"""

from __future__ import annotations

import json
from datetime import date
from typing import Any

import click


@click.command("changying-refresh")
@click.option("--date", "target", default=None, help="目标日期 YYYY-MM-DD（缺省今天）")
@click.option("--top-n", default=20, type=int, help="沉淀标的数量（默认 20）")
@click.option("--min-mcap-yi", default=100.0, type=float, help="总市值下限（亿元，默认 100）")
@click.option("--min-score", default=15.0, type=float, help="分类得分下限")
@click.option("--markets", default="SH,SZ", help="扫描市场，逗号分隔（默认 SH,SZ）")
def changying_refresh(
    target: str | None,
    top_n: int,
    min_mcap_yi: float,
    min_score: float,
    markets: str,
) -> None:
    """用 TDX 在线数据刷新长盈标的池并沉淀到本地 SQLite。

    建议放到系统 cron（每天凌晨 0 点）：

      0 0 * * * easy-tdx changying-refresh >> /tmp/changying.log 2>&1
    """
    from easy_tdx.fundamental.changying_pool import refresh_changying_pool

    t = date.fromisoformat(target) if target else None
    mk = tuple(m.strip().upper() for m in markets.split(",") if m.strip())
    out: dict[str, Any] = refresh_changying_pool(
        t,
        markets=mk or ("SH", "SZ"),
        top_n=top_n,
        min_mcap_yi=min_mcap_yi,
        min_score=min_score,
    )
    # 只打印摘要，不打印完整明细（明细已入库，cron 日志保持简洁）
    summary = {
        "updated_at": out.get("updated_at"),
        "date": out.get("date"),
        "count": out.get("count"),
        "min_mcap_yi": out.get("min_mcap_yi"),
        "by_category": out.get("by_category"),
        "total_scanned": out.get("total_scanned"),
        "top": [
            f"{r['market']}:{r['code']} {r['category']} {r['score']:.1f}"
            for r in out.get("results", [])[:5]
        ],
    }
    click.echo(json.dumps(summary, ensure_ascii=False, indent=2))


@click.command("changying-mark")
@click.option("--date", "target", default=None, help="目标日期 YYYY-MM-DD（缺省今天）")
@click.option("--min-mcap-yi", default=100.0, type=float, help="总市值下限（亿元，默认 100）")
@click.option("--min-score", default=15.0, type=float, help="分类得分下限（0=有分类即标记）")
@click.option("--markets", default="SH,SZ", help="扫描市场，逗号分隔（默认 SH,SZ）")
@click.option("--force", is_flag=True, help="跳过半成品保护校验（确认数据正常后强制刷新）")
@click.option("--top", "top_show", default=10, type=int, help="摘要展示前 N 只（默认 10）")
def changying_mark(
    target: str | None,
    min_mcap_yi: float,
    min_score: float,
    markets: str,
    force: bool,
    top_show: int,
) -> None:
    """全市场标记：A 股市值 >=100 亿标的全部标记树/粮/菜并全量落库。

    与 changying-refresh（top 20 精选池）的区别：本命令面向全市场，
    不做 top-N 截断；调度频次为财报对齐的半年频（1/7 月首个周六主跑，
    季报兜底），手动可用 --force 随时刷新。

    建议放到系统 cron（每周六 00:05，脚本内自带半年窗口锁）：

      5 0 * * 6 easy-tdx changying-mark >> /tmp/changying_mark.log 2>&1
    """
    from easy_tdx.fundamental.marks import refresh_changying_marks

    t = date.fromisoformat(target) if target else None
    mk = tuple(m.strip().upper() for m in markets.split(",") if m.strip())
    out: dict[str, Any] = refresh_changying_marks(
        t,
        markets=mk or ("SH", "SZ"),
        min_mcap_yi=min_mcap_yi,
        min_score=min_score,
        force=force,
    )
    summary = {
        "updated_at": out.get("updated_at"),
        "date": out.get("trade_date"),
        "count": out.get("count"),
        "min_mcap_yi": out.get("min_mcap_yi"),
        "min_score": out.get("min_score"),
        "by_category": out.get("by_category"),
        "total_scanned": out.get("total_scanned"),
        "top": [
            {
                "symbol": r.get("market", "") + ":" + r.get("code", ""),
                "category": r.get("category"),
                "score": r.get("score"),
                "total_mcap_yi": r.get("total_mcap_yi"),
            }
            for r in out.get("results", [])[:top_show]
        ],
    }
    click.echo(json.dumps(summary, ensure_ascii=False, indent=2))


@click.command("audit-accuracy")
@click.option("--samples", default=30, type=int, help="每类抽样标的数（默认 30）")
@click.option("--chanlun-limit", default=15, type=int, help="缠论信号审计标的数（默认 15）")
@click.option("--skip-chanlun", is_flag=True, help="跳过缠论审计（只跑长盈分层 + 图表对账）")
@click.option("--seed", default=42, type=int, help="抽样种子（保证审计可复现）")
def audit_accuracy(
    samples: int,
    chanlun_limit: int,
    skip_chanlun: bool,
    seed: int,
) -> None:
    """模型准确性审计：长盈分层前瞻收益 + 缠论信号质量 + 图表对账。

    长盈前瞻收益以最近 5 个已过去季末为基期（保证 250 日窗口真实可算）；
    缠论信号走 signal_ledger 统一台账（与面板同口径）；
    报告落盘 ~/.easy_tdx/audit/accuracy_<date>.json + .md，
    Web 端 /audit/accuracy 可查看最新报告。
    所有数字为真实行情计算；数据缺失输出 null，绝不合成。
    """
    from easy_tdx.audit.accuracy import run_accuracy_audit

    report = run_accuracy_audit(
        samples=samples,
        chanlun_limit=chanlun_limit,
        seed=seed,
        skip_chanlun=skip_chanlun,
    )
    summary = {
        "generated_at": report.get("generated_at"),
        "bases": report.get("bases"),
        "marks": report.get("marks"),
        "files": report.get("files"),
        "changying_per_class": {
            cat: {k: s for k, s in stats.items() if k in ("samples", "pit_violations", "data_missing")}
            for cat, stats in ((report.get("changying") or {}).get("per_class") or {}).items()
        },
        "chanlun_signal_count": (report.get("chanlun") or {}).get("signal_count"),
        "chanlun_by_type": (report.get("chanlun") or {}).get("by_type"),
        "chart_mismatches": (report.get("chart_consistency") or {}).get("mismatches"),
    }
    click.echo(json.dumps(summary, ensure_ascii=False, indent=2))
