"""缠论分析命令。"""

from __future__ import annotations

import json
from typing import Any

import click


@click.command()
@click.argument("market")
@click.argument("code")
@click.option(
    "--period", default="DAILY", help="K线周期: DAILY/5MIN/15MIN/30MIN/60MIN/1MIN/WEEKLY/MONTHLY"
)
@click.option("--count", default=800, type=int, help="K线数量")
@click.option("--adjust", default="NONE", help="复权: NONE/QFQ/HFQ")
@click.option(
    "--multi-level",
    "low_level_period",
    default=None,
    help="低级别周期（多级别联立），如 30MIN；分析高级别最后一笔在低级别中的走势",
)
@click.option("--table", "use_table", is_flag=True, help="表格输出")
@click.option("--output", "output_fmt", type=click.Choice(["json", "table", "csv"]), default="json")
def chanlun(
    market: str,
    code: str,
    period: str,
    count: int,
    adjust: str,
    low_level_period: str | None,
    use_table: bool,
    output_fmt: str,
) -> None:
    """缠论分析：计算 K 线的笔、中枢等缠论指标。

    示例：

      easy-tdx chanlun SZ 000001

      easy-tdx chanlun SH 600519 --adjust QFQ --table

      easy-tdx chanlun SZ 000001 --period 30MIN

      easy-tdx chanlun SZ 000001 --multi-level 30MIN --table

      easy-tdx chanlun SZ 000001 --multi-level 5MIN
    """
    from ..chanlun.analyser import ChanlunAnalyser
    from .conn import get_mac_client
    from .parsers import parse_adjust, parse_market, parse_period

    mkt = parse_market(market)
    with get_mac_client() as client:
        df = client.get_stock_kline(
            mkt,
            code,
            period=parse_period(period),
            start=0,
            count=count,
            adjust=parse_adjust(adjust),
        )

        analyser = ChanlunAnalyser(code=code, frequency=period)
        result = analyser.process_klines(df)

        result_dict = result.to_dict()

        # 多级别联立分析（需要在 with 块内使用 client 获取低级别数据）
        multi_level_info: dict[str, Any] | None = None
        if low_level_period is not None:
            multi_level_info = _run_multi_level(
                client, mkt, code, period, low_level_period, count, adjust, analyser, result
            )
            if multi_level_info is not None:
                result_dict["multi_level"] = multi_level_info

    fmt = "table" if use_table else output_fmt
    if fmt == "json":
        click.echo(json.dumps(result_dict, ensure_ascii=False, indent=2))
    elif fmt == "table":
        _print_table(result_dict)
    else:
        click.echo(json.dumps(result_dict, ensure_ascii=False))


def _print_table(result: dict[str, Any]) -> None:
    """以表格形式输出缠论分析结果。"""
    click.echo(f"标的: {result['code']}  周期: {result['frequency']}")
    click.echo(f"原始K线: {result['kline_count']}  缠论K线: {result['ckline_count']}")
    click.echo(
        f"分型: {result['fractal_count']}  笔: {result['bi_count']}  "
        f"中枢: {result['zs_count']}  线段: {result.get('xd_count', 0)}"
    )
    mmd_count = result.get("mmd_count", 0)
    bc_count = result.get("bc_count", 0)
    if mmd_count or bc_count:
        click.echo(f"买卖点: {mmd_count}  背驰: {bc_count}")
    click.echo()

    if result["bis"]:
        click.echo("── 笔 ──")
        for bi in result["bis"]:
            direction = "↑" if bi["direction"] == "up" else "↓"
            done = "✓" if bi["done"] else "…"
            click.echo(
                f"  [{bi['index']}] {direction} "
                f"{bi['start_date']} → {bi['end_date']} "
                f"h={bi['high']} l={bi['low']} {done}"
            )
        click.echo()

    if result["zss"]:
        click.echo("── 中枢 ──")
        for zs in result["zss"]:
            done = "✓" if zs["done"] else "…"
            click.echo(
                f"  [{zs['index']}] "
                f"{zs['start_date'] or '—'} → {zs['end_date'] or '—'} "
                f"zg={zs['zg']} zd={zs['zd']} "
                f"gg={zs['gg']} dd={zs['dd']} "
                f"lines={zs['line_count']} {done}"
            )
        click.echo()

    if result.get("xds"):
        click.echo("── 线段 ──")
        for xd in result["xds"]:
            direction = "↑" if xd["direction"] == "up" else "↓"
            click.echo(
                f"  [{xd['index']}] {direction} "
                f"{xd['start_date']} → {xd['end_date']} "
                f"h={xd['high']} l={xd['low']}"
            )
        click.echo()

    if result.get("mmds"):
        click.echo("── 买卖点 ──")
        for mmd in result["mmds"]:
            click.echo(f"  {mmd['type']} ({mmd['date'] or '—'}): {mmd['msg']}")
        click.echo()

    if result.get("bcs"):
        click.echo("── 背驰 ──")
        for bc in result["bcs"]:
            status = "✓" if bc["bc"] else "✗"
            prev = bc["prev_date"] or "—"
            curr = bc["curr_date"] or "—"
            click.echo(f"  [{status}] {bc['type']} ({prev} → {curr}): {bc['msg']}")

    if result.get("multi_level"):
        ml = result["multi_level"]
        click.echo("── 多级别联立 ──")
        click.echo(f"  高级别: {ml.get('high_level', '?')}  低级别: {ml.get('low_level', '?')}")
        qs = ml.get("low_level_qs", {})
        if qs:
            direction = qs.get("trend_direction")
            dir_str = {"up": "↑ 上升", "down": "↓ 下降"}.get(str(direction), "— 盘整")
            click.echo(f"  低级别笔: {qs.get('bi_count', 0)}  中枢: {qs.get('zs_count', 0)}")
            click.echo(
                f"  趋势方向: {dir_str}  "
                f"趋势: {'是' if qs.get('has_trend') else '否'}  "
                f"盘整: {'是' if qs.get('has_consolidation') else '否'}"
            )
            click.echo(
                f"  笔重叠: {'是' if qs.get('bi_overlap') else '否'}  "
                f"背驰可能: {'是' if qs.get('divergence_possible') else '否'}"
            )
        click.echo()


@click.command("advice")
@click.argument("market")
@click.argument("code")
@click.option("--period", default="DAILY", help="K线周期: DAILY/5MIN/15MIN/30MIN/60MIN")
@click.option("--count", default=500, type=int, help="K线数量")
@click.option("--max-hold", default=10, type=int, help="建议最大持有根数（1-60）")
@click.option(
    "--output",
    "output_fmt",
    type=click.Choice(["json", "table", "csv", "md"]),
    default="json",
)
def advice_simulate(
    market: str,
    code: str,
    period: str,
    count: int,
    max_hold: int,
    output_fmt: str,
) -> None:
    """V102 建议回放实证：对 3买/3卖 信号生成入场/止损/止盈建议并在历史行情回放。

    回答「本标的最近出现的 3买/3卖 信号，按模型给的建议执行，历史结果如何」——
    每笔的出场原因（止损/止盈/到期）与收益，以及批量胜率/平均收益汇总。

    示例：

      easy-tdx advice SZ 000001

      easy-tdx advice SZ 000001 --max-hold 15 --table
    """
    from ..backtest.advice_simulator import collect_signal_advices, simulate_advice_batch
    from ..chanlun.analyser import ChanlunAnalyser
    from .conn import get_mac_client
    from .parsers import parse_market, parse_period

    mkt = parse_market(market)
    with get_mac_client() as client:
        df = client.get_stock_kline(
            mkt,
            code,
            period=parse_period(period),
            start=0,
            count=count,
        )
        if df is None or len(df) < 30:
            click.echo(
                json.dumps(
                    {"symbol": f"{market}{code}", "error": "行情数据不足（<30 根），无法回放建议"},
                    ensure_ascii=False,
                )
            )
            return

        analyser = ChanlunAnalyser(code=code, frequency=period)
        result = analyser.process_klines(df)
        closes = [float(k.close) for k in result.klines]
        highs = [float(k.high) for k in result.klines]
        lows = [float(k.low) for k in result.klines]
        advices = collect_signal_advices(result, closes, highs, lows, max_hold)

        if not advices:
            click.echo(
                json.dumps(
                    {
                        "symbol": f"{market}{code}",
                        "signal_count": len(result.mmds),
                        "advice_count": 0,
                        "message": f"近 {len(closes)} 根K线未发现 3买/3卖 信号，无法生成可回放建议",
                    },
                    ensure_ascii=False,
                )
            )
            return

        report = simulate_advice_batch(highs, lows, closes, advices)

    if output_fmt == "csv":
        rows = []
        rows.append(
            "symbol,advice_count,win_rate,avg_return,total_return,stop_rate,tp_rate,expire_rate"
        )
        rows.append(
            ",".join(
                [
                    f"{market}{code}",
                    str(report["count"]),
                    f"{report['win_rate'] * 100:.1f}%",
                    f"{report['avg_return']:+.2f}%",
                    f"{report['total_return']:+.2f}%",
                    f"{report['stop_rate'] * 100:.1f}%",
                    f"{report['tp_rate'] * 100:.1f}%",
                    f"{report['expire_rate'] * 100:.1f}%",
                ]
            )
        )
        rows.append("")
        rows.append("no,entry_price,stop_loss,take_profit_1,exit_price,exit_reason,return_pct")
        for i, (adv, t) in enumerate(zip(advices, report["trades"])):
            rows.append(
                ",".join(
                    [
                        str(i + 1),
                        f"{adv['entry_price']:.2f}",
                        f"{adv['stop_loss']:.2f}",
                        f"{adv['take_profit_1']:.2f}",
                        f"{t['exit_price']:.2f}",
                        t["exit_reason"],
                        f"{t['return_pct']:+.2f}",
                    ]
                )
            )
        click.echo("\n".join(rows))
    elif output_fmt == "table":
        click.echo(
            f"标的 {market}{code} | 建议 {report['count']} 笔 | "
            f"胜率 {report['win_rate'] * 100:.0f}% | "
            f"平均 {report['avg_return']:+.2f}% | 累计 {report['total_return']:+.2f}%"
        )
        click.echo(
            f"出场分布: 止损 {report['stop_rate'] * 100:.0f}% / "
            f"止盈 {report['tp_rate'] * 100:.0f}% / 到期 {report['expire_rate'] * 100:.0f}%"
        )
        click.echo(
            f"{'#':>3} {'入场':>9} {'止损':>9} {'止盈1':>9} {'出场价':>9} {'原因':>4} {'收益%':>8}"
        )
        for i, (adv, t) in enumerate(zip(advices, report["trades"])):
            reason = {"stop": "止损", "tp1": "止盈", "expire": "到期"}.get(
                t["exit_reason"], t["exit_reason"]
            )
            click.echo(
                f"{i + 1:>3} {adv['entry_price']:>9.2f} {adv['stop_loss']:>9.2f} "
                f"{adv['take_profit_1']:>9.2f} {t['exit_price']:>9.2f} {reason:>4} "
                f"{t['return_pct']:>+8.2f}%"
            )
    elif output_fmt == "md":
        # V370: Markdown 报告（与 offline advice --output md / advice-batch --md 对齐）
        reason_cn = {"stop": "止损", "tp1": "止盈", "expire": "到期", "invalid": "无效"}
        click.echo(f"# 在线 V102 建议回放报告（{market}{code}）")
        click.echo()
        click.echo(
            f"K线 **{len(closes)}** 根 | 缠论信号 **{len(result.mmds)}** | "
            f"建议 **{report['count']}** 笔"
        )
        click.echo()
        click.echo("| # | 入场 | 止损 | 止盈1 | 出场价 | 原因 | 收益% |")
        click.echo("|---|-----|-----|------|-------|------|-------|")
        for i, (adv, t) in enumerate(zip(advices, report["trades"])):
            reason = reason_cn.get(t["exit_reason"], t["exit_reason"])
            click.echo(
                f"| {i + 1} | {adv['entry_price']:.2f} | {adv['stop_loss']:.2f} | "
                f"{adv['take_profit_1']:.2f} | {t['exit_price']:.2f} | {reason} | "
                f"{t['return_pct']:+.2f} |"
            )
        click.echo()
        click.echo(
            f"**汇总**：胜率 {report['win_rate'] * 100:.0f}% | "
            f"平均收益 {report['avg_return']:+.2f}% | 累计 {report['total_return']:+.2f}%"
        )
        click.echo(
            f"**出场分布**：止损 {report['stop_rate'] * 100:.0f}% / "
            f"止盈 {report['tp_rate'] * 100:.0f}% / 到期 {report['expire_rate'] * 100:.0f}%"
        )
    else:
        click.echo(
            json.dumps(
                {
                    "symbol": f"{market}{code}",
                    "signal_count": len(result.mmds),
                    "advice_count": len(advices),
                    "report": report,
                },
                ensure_ascii=False,
                indent=2,
            )
        )


def _run_multi_level(
    client: Any,
    mkt: Any,
    code: str,
    high_period: str,
    low_period: str,
    count: int,
    adjust: str,
    high_analyser: Any,
    high_result: Any,
) -> dict[str, Any] | None:
    """运行多级别联立分析。

    获取低级别数据，分析高级别最后一笔在低级别中的走势结构。

    Args:
        client: TdxClient 实例
        mkt: Market 枚举值
        code: 股票代码
        high_period: 高级别周期
        low_period: 低级别周期
        count: K线数量
        adjust: 复权方式
        high_analyser: 高级别分析器（已处理）
        high_result: 高级别分析结果

    Returns:
        多级别分析信息字典，或 None（数据不足时）
    """
    from ..chanlun.analyser import ChanlunAnalyser
    from ..chanlun.multi_level import MultiLevelAnalyser
    from .parsers import parse_adjust, parse_period

    # 高级别最后一笔
    if not high_result.bis:
        return None

    last_bi = high_result.bis[-1]

    # 获取低级别数据（需要更多 K 线来覆盖高级别笔的时间范围）
    df_low = client.get_stock_kline(
        mkt,
        code,
        period=parse_period(low_period),
        start=0,
        count=min(count * 8, 8000),  # 低级别需要更多数据
        adjust=parse_adjust(adjust),
    )

    low_analyser = ChanlunAnalyser(code=code, frequency=low_period)

    mla = MultiLevelAnalyser()
    mla.add_level("high", high_analyser)
    mla.add_level("low", low_analyser)
    # 高级别已经处理过，只需注册；低级别需要处理
    mla.process("low", df_low)

    qs = mla.query_low_level_qs("high", "low", last_bi)

    return {
        "high_level": high_period,
        "low_level": low_period,
        "last_bi_index": last_bi.index if hasattr(last_bi, "index") else None,
        "low_level_qs": qs,
    }
