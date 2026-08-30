"""财务数据命令。"""

from __future__ import annotations

import json
from typing import Any

import click


@click.command("f10")
@click.argument("code")
@click.option(
    "--type",
    "report_type",
    type=click.Choice(["lrb", "fzb", "llb"], case_sensitive=False),
    default="lrb",
    help="报表类型: lrb(利润表) / fzb(资产负债表) / llb(现金流量表)",
)
@click.option("--num", default=8, type=int, help="取最近 N 期（默认 8）")
@click.option("--table", "use_table", is_flag=True, help="表格输出")
@click.option("--output", "output_fmt", type=click.Choice(["json", "table", "csv"]), default="json")
def f10(code: str, report_type: str, num: int, use_table: bool, output_fmt: str) -> None:
    """获取财报三表（新浪数据源，独立于 TDX 行情服务器）。

    \b
    报表类型：
      lrb  利润表（默认）
      fzb  资产负债表
      llb  现金流量表

    \b
    示例：

      easy-tdx f10 600519                          # 茅台利润表，最近 8 期

      easy-tdx f10 600519 --type fzb --num 4       # 资产负债表，最近 4 期

      easy-tdx f10 000001 --type llb --table       # 平安现金流量表，表格输出
    """
    from ..sina import SinaClient, SinaError
    from .output import print_error, print_output

    fmt = "table" if use_table else output_fmt
    client = SinaClient()
    try:
        df = client.get_financial_report(code, report_type=report_type, num=num)
    except SinaError as e:
        print_error(str(e))
        raise SystemExit(1) from e
    print_output(df, fmt)


@click.command("fund-flow")
@click.argument("market")
@click.argument("code")
@click.option("--start", default=0, type=int, help="起始偏移")
@click.option("--count", default=30, type=int, help="请求数量")
def fund_flow(market: str, code: str, start: int, count: int) -> None:
    """获取历史资金流向（暂未实现）。

    示例：

      easy-tdx fund-flow SZ 000001
    """
    raise click.UsageError("fund-flow 命令暂未实现，请使用 TdxClient.get_history_fund_flow() API")


@click.command("gpcw-cache")
@click.option("--action", type=click.Choice(["stats", "warm", "clear"]), default="stats")
@click.option(
    "--date",
    "target_date",
    default=None,
    help="warm 用目标日期 YYYY-MM-DD（自动选该日期的报告期）",
)
@click.option("--table", "use_table", is_flag=True, help="表格输出")
def gpcw_cache(action: str, target_date: str | None, use_table: bool) -> None:
    """gpcw 指标帧缓存管理（V89，SQLite）。

    \b
    动作：
      stats  查看缓存统计（已缓存报告期/行数/库大小/格式版本）
      warm   预生成缓存（解析缺失报告期的指标帧并落盘）
      clear  清空全部缓存

    \b
    示例：
      easy-tdx gpcw-cache stats --table
      easy-tdx gpcw-cache warm --date 2026-09-01
      easy-tdx gpcw-cache clear
    """
    from easy_tdx.fundamental import cache

    from .output import print_output

    if action == "stats":
        stats = cache.cache_stats()
        if use_table:
            rows = [[z["filename"], z["rows"], z["built_at"]] for z in stats["zips"]]
            print_output(
                _df_from_rows(rows, ["报告期", "行数", "生成时间"]),
                "table",
            )
        click.echo(
            json.dumps(
                {
                    "format_version": stats["format_version"],
                    "db_path": stats["db_path"],
                    "db_bytes": stats["db_bytes"],
                    "zips_count": stats["zips_count"],
                    "total_rows": stats["total_rows"],
                },
                ensure_ascii=False,
            )
        )
        return

    if action == "clear":
        n = cache.clear_cache()
        click.echo(json.dumps({"cleared_zips": n}, ensure_ascii=False))
        return

    # warm
    if not target_date:
        raise click.UsageError("warm 需要 --date YYYY-MM-DD 指定目标日期")
    from datetime import date as _date

    from easy_tdx.fundamental.pipeline import pick_report_zips

    try:
        target = _date.fromisoformat(target_date)
    except ValueError:
        raise click.UsageError("--date 格式应为 YYYY-MM-DD") from None
    zips = pick_report_zips(target)
    if not zips:
        raise click.UsageError("目标日期无可用的 gpcw 财报文件")
    result = cache.warm(zips)
    click.echo(json.dumps(result, ensure_ascii=False))


def _df_from_rows(rows: list[list[str | int]], cols: list[str]) -> Any:
    """把行列表转成打印用 DataFrame（避免引入额外依赖）。"""
    import pandas as pd

    return pd.DataFrame(rows, columns=cols)
