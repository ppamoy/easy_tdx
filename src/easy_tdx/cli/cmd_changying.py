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
