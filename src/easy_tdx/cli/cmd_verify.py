"""模型验证报告命令：verify —— 对单标的跑完整准确度验证套件。

跑回测得到绩效 + 信号准确度（引擎内置，V95），并可选追加分段稳健性（V97）、
样本外验证（V105）与模型可信度综合评分（V101）。

用法::

    easy-tdx verify SZ 000001 --strategy ma_cross \
        --params '{"fast": 5, "slow": 20}' --segments 3 --out-of-sample

输出 JSON（默认）：performance / signal_accuracy / segment_robustness /
out_of_sample / model_trust / verdict。
"""

from __future__ import annotations

import json
from typing import Any

import click


@click.command()
@click.argument("market")
@click.argument("code")
@click.option("--strategy", "strategy_name", default="ma_cross", help="注册表中的策略名")
@click.option(
    "--params",
    "params_json",
    default="{}",
    help="策略参数 JSON，如 {'fast': 5, 'slow': 20}",
)
@click.option("--count", default=800, type=int, help="K线数量")
@click.option(
    "--period",
    default="DAILY",
    help="K线周期: DAILY/5MIN/15MIN/30MIN/60MIN/1MIN/WEEKLY/MONTHLY",
)
@click.option("--adjust", default="NONE", help="复权: NONE/QFQ/HFQ")
@click.option("--cash", default=1_000_000.0, type=float, help="初始资金")
@click.option("--commission", default=0.0003, type=float, help="佣金率")
@click.option("--slippage", default=0.0, type=float, help="滑点")
@click.option("--execution", default="next_open", help="成交规则: next_open/next_close")
@click.option("--segments", default=None, type=int, help="分段稳健性段数（2~6，不填则跳过）")
@click.option("--out-of-sample", "run_oos", is_flag=True, help="样本外验证（训练/持有切分）")
@click.option("--train-ratio", "train_ratio", default=0.7, type=float, help="样本外训练段占比")
@click.option("--output", "output_fmt", type=click.Choice(["json"]), default="json")
@click.option(
    "--output-file",
    "output_file",
    default=None,
    type=str,
    help="把 JSON 报告写入文件（默认打印到 stdout）",
)
def verify(
    market: str,
    code: str,
    strategy_name: str,
    params_json: str,
    count: int,
    period: str,
    adjust: str,
    cash: float,
    commission: float,
    slippage: float,
    execution: str,
    segments: int | None,
    run_oos: bool,
    train_ratio: float,
    output_fmt: str,
    output_file: str | None,
) -> None:
    """模型验证：单标的完整准确度报告。"""
    from ..cli.conn import get_mac_client
    from ..cli.parsers import parse_adjust, parse_market, parse_period

    try:
        params: dict[str, Any] = json.loads(params_json) if params_json.strip() else {}
    except json.JSONDecodeError as exc:
        click.echo("错误: --params 不是合法 JSON: " + str(exc), err=True)
        raise SystemExit(1)

    from ..backtest import BacktestEngine
    from ..backtest.strategies import get_registry

    # 1. 策略
    try:
        entry = get_registry().get(strategy_name)
    except KeyError as exc:
        click.echo("错误: " + str(exc), err=True)
        raise SystemExit(1)
    strategy = entry.build(params)

    # 2. 行情
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
    if df is None or len(df) < 30:
        click.echo("错误: 行情数据不足 30 根", err=True)
        raise SystemExit(1)

    # 3. 回测（引擎内置 signal_accuracy V95）
    engine = BacktestEngine(
        strategy=strategy,
        cash=cash,
        commission=commission,
        slippage=slippage,
        execution=execution,
    )
    result = engine.run(df)
    result_dict = result.to_dict()

    # 4. 分段稳健性（V97，可选）
    if segments is not None:
        if not 2 <= segments <= 6:
            click.echo("错误: --segments 需在 2~6 之间", err=True)
            raise SystemExit(1)
        from ..backtest.robustness import compute_segment_robustness

        result_dict["segment_robustness"] = compute_segment_robustness(
            df,
            lambda: entry.build(params),
            segments=segments,
            cash=cash,
            commission=commission,
            slippage=slippage,
            execution=execution,
        )

    # 5. 模型可信度（V101）
    try:
        from ..backtest.model_trust import compute_model_trust

        result_dict["model_trust"] = compute_model_trust(
            result_dict.get("performance"),
            result_dict.get("signal_accuracy"),
            result_dict.get("segment_robustness"),
        )
    except Exception:
        result_dict["model_trust"] = None

    # 6. 样本外验证（V105，可选）
    if run_oos:
        try:
            from ..backtest.out_of_sample import compute_out_of_sample

            result_dict["out_of_sample"] = compute_out_of_sample(
                df,
                lambda: entry.build(params),
                train_ratio=train_ratio,
                cash=cash,
                commission=commission,
                slippage=slippage,
                execution=execution,
            )
        except Exception:
            result_dict["out_of_sample"] = None

    # 7. 汇总结论
    verdict_parts: list[str] = []
    mt = result_dict.get("model_trust") or {}
    if mt.get("grade"):
        trust_str = (
            "模型可信度 " + str(mt.get("grade")) + "（"
            + str(int(mt.get("score", 0))) + "/100）"
        )
        verdict_parts.append(trust_str)
    sa = result_dict.get("signal_accuracy") or {}
    if sa.get("verdict"):
        verdict_parts.append(str(sa["verdict"]))
    sr = result_dict.get("segment_robustness") or {}
    if sr.get("verdict"):
        verdict_parts.append(str(sr["verdict"]))
    oos = result_dict.get("out_of_sample") or {}
    if oos.get("verdict"):
        verdict_parts.append(str(oos["verdict"]))
    result_dict["verdict"] = "；".join(verdict_parts) if verdict_parts else "无验证结论（数据不足）"

    text = json.dumps(result_dict, ensure_ascii=False, indent=2, default=str)
    if output_file:
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(text + "\n")
        click.echo("已写入 " + output_file)
    else:
        click.echo(text)


@click.command("verify-multi")
@click.argument("stocks")
@click.option("--strategy", "strategy_name", default="ma_cross", help="注册表中的策略名")
@click.option("--params", "params_json", default="{}", help="策略参数 JSON")
@click.option("--count", default=500, type=int, help="每只标的 K线数量")
@click.option(
    "--period",
    default="DAILY",
    help="K线周期: DAILY/5MIN/15MIN/30MIN/60MIN/1MIN/WEEKLY/MONTHLY",
)
@click.option("--adjust", default="NONE", help="复权: NONE/QFQ/HFQ")
@click.option("--cash", default=1_000_000.0, type=float, help="初始资金")
@click.option("--commission", default=0.0003, type=float, help="佣金率")
@click.option("--slippage", default=0.0, type=float, help="滑点")
@click.option("--max-stocks", "max_stocks", default=20, type=int, help="最多验证多少只标的")
@click.option("--segments", default=None, type=int, help="分段稳健性段数（2~6，不填则跳过）")
@click.option("--out-of-sample", "run_oos", is_flag=True, help="样本外验证（训练/持有切分）")
@click.option("--train-ratio", "train_ratio", default=0.7, type=float, help="样本外训练段占比")
@click.option(
    "--output-file",
    "output_file",
    default=None,
    type=str,
    help="把 JSON 报告写入文件（默认打印到 stdout）",
)
def verify_multi(
    stocks: str,
    strategy_name: str,
    params_json: str,
    count: int,
    period: str,
    adjust: str,
    cash: float,
    commission: float,
    slippage: float,
    max_stocks: int,
    segments: int | None,
    run_oos: bool,
    train_ratio: float,
    output_file: str | None,
) -> None:
    """批量模型验证：对多只标的跑同一策略，按模型可信度排名选股。

    STOCKS 格式: "SZ 000001,SH 600519"

    示例::

      easy-tdx verify-multi "SZ 000001,SZ 000002,SH 600519" \
          --strategy ma_cross --params '{"fast": 5, "slow": 20}' \
          --segments 3 --out-of-sample

    输出 JSON：symbols 数组（含 total_return/win_rate/hit_rate/trust，可选
    overfit_likely/oos_degraded 等验证结论），按可信度降序。
    """
    from ..cli.conn import get_mac_client
    from ..cli.parsers import parse_adjust, parse_period, parse_stocks

    try:
        params: dict[str, Any] = json.loads(params_json) if params_json.strip() else {}
    except json.JSONDecodeError as exc:
        click.echo("错误: --params 不是合法 JSON: " + str(exc), err=True)
        raise SystemExit(1)

    from ..backtest import BacktestEngine
    from ..backtest.strategies import get_registry

    try:
        entry = get_registry().get(strategy_name)
    except KeyError as exc:
        click.echo("错误: " + str(exc), err=True)
        raise SystemExit(1)

    market_codes = parse_stocks(stocks)[:max_stocks]
    if not market_codes:
        click.echo('错误: 未解析到任何标的（格式如 "SZ 000001,SH 600519"）', err=True)
        raise SystemExit(1)

    rows: list[dict[str, Any]] = []
    failures: list[str] = []
    with get_mac_client() as client:
        for market_int, code in market_codes:
            symbol = ("SZ" if market_int == 0 else ("SH" if market_int == 1 else "BJ")) + code
            try:
                df = client.get_stock_kline(
                    market_int,
                    code,
                    period=parse_period(period),
                    start=0,
                    count=count,
                    adjust=parse_adjust(adjust),
                )
                if df is None or len(df) < 30:
                    failures.append(symbol + "(行情不足)")
                    continue
                strategy = entry.build(params)
                engine = BacktestEngine(
                    strategy=strategy,
                    cash=cash,
                    commission=commission,
                    slippage=slippage,
                )
                bt_result = engine.run(df)  # 引擎内置 signal_accuracy(V95)
                bp = bt_result.performance
                # 模型可信度（V101）
                mt: dict[str, Any] = {}
                try:
                    from ..backtest.model_trust import compute_model_trust

                    mt = compute_model_trust(bp, bt_result.signal_accuracy, None)
                except Exception:
                    mt = {}
                hit_rate: float | None = None
                excess_hit_rate: float | None = None
                sa = bt_result.signal_accuracy or {}
                buy = sa.get("buy") or {}
                horizons = buy.get("horizons") or {}
                h5 = horizons.get("5") or horizons.get("3")
                if h5 and h5.get("count", 0) > 0:
                    hit_rate = float(h5["hit_rate"])
                    excess_hit_rate = float(h5.get("excess_hit_rate", 0.0))
                row: dict[str, Any] = {
                    "symbol": symbol,
                    "total_return": bp.get("total_return", 0.0),
                    "win_rate": bp.get("win_rate", 0.0),
                    "trades": int(bp.get("total_trades", 0)),
                    "hit_rate": hit_rate,
                    "excess_hit_rate": excess_hit_rate,
                    "trust_score": mt.get("score"),
                    "trust_grade": mt.get("grade"),
                }
                # V132: 可选的分段稳健性（V97）与样本外验证（V105）
                if segments is not None:
                    try:
                        from ..backtest.robustness import compute_segment_robustness

                        robust = compute_segment_robustness(
                            df,
                            lambda: entry.build(params),
                            segments=segments,
                            cash=cash,
                            commission=commission,
                            slippage=slippage,
                        )
                        row["overfit_likely"] = robust.get("overfit_likely", False)
                        row["robust_verdict"] = robust.get("verdict", "")
                    except Exception:  # noqa: BLE001
                        row["overfit_likely"] = None
                        row["robust_verdict"] = "分段稳健性计算失败"
                if run_oos:
                    try:
                        from ..backtest.out_of_sample import compute_out_of_sample

                        oos = compute_out_of_sample(
                            df,
                            lambda: entry.build(params),
                            train_ratio=train_ratio,
                            cash=cash,
                            commission=commission,
                            slippage=slippage,
                        )
                        row["oos_degraded"] = oos.get("degraded", False)
                        row["oos_verdict"] = oos.get("verdict", "")
                        row["train_return"] = (oos.get("train") or {}).get("total_return")
                        row["test_return"] = (oos.get("test") or {}).get("total_return")
                    except Exception:  # noqa: BLE001
                        row["oos_degraded"] = None
                        row["oos_verdict"] = "样本外验证计算失败"
                rows.append(row)
            except Exception as exc:  # noqa: BLE001 — 单只失败跳出循环前记录
                failures.append(symbol + "(" + str(exc) + ")")

    # 按可信度降序（缺可信度排最后）
    rows.sort(key=lambda r: (r["trust_score"] is not None, r["trust_score"]), reverse=True)
    out = {
        "strategy": strategy_name,
        "total": len(market_codes),
        "verified": len(rows),
        "symbols": rows,
        "failures": failures,
    }
    text = json.dumps(out, ensure_ascii=False, indent=2, default=str)
    if output_file:
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(text + "\n")
        click.echo("已写入 " + output_file)
    else:
        click.echo(text)


@click.command("verify-portfolio")
@click.argument("stocks")
@click.option("--strategy", "strategy_name", default="ma_cross", help="注册表中的策略名")
@click.option("--params", "params_json", default="{}", help="策略参数 JSON")
@click.option("--count", default=500, type=int, help="每只标的 K线数量")
@click.option(
    "--period",
    default="DAILY",
    help="K线周期: DAILY/5MIN/15MIN/30MIN/60MIN/1MIN/WEEKLY/MONTHLY",
)
@click.option("--adjust", default="NONE", help="复权: NONE/QFQ/HFQ")
@click.option("--cash", default=1_000_000.0, type=float, help="组合总资金（均分）")
@click.option("--commission", default=0.0003, type=float, help="佣金率")
@click.option("--slippage", default=0.0, type=float, help="滑点")
@click.option("--out-of-sample", "run_oos", is_flag=True, help="组合级样本外验证（V126）")
@click.option(
    "--output-file",
    "output_file",
    default=None,
    type=str,
    help="把 JSON 报告写入文件（默认打印到 stdout）",
)
def verify_portfolio(
    stocks: str,
    strategy_name: str,
    params_json: str,
    count: int,
    period: str,
    adjust: str,
    cash: float,
    commission: float,
    slippage: float,
    run_oos: bool,
    output_file: str | None,
) -> None:
    """组合模型验证：多标的跑同一策略，输出组合绩效 + 组合准确度聚合 + 组合可信度。

    STOCKS 格式: "SZ 000001,SZ 000002,SH 600519"，资金按数量均分。

    示例::

      easy-tdx verify-portfolio "SZ 000001,SZ 000002,SH 600519" \
          --strategy ma_cross --params '{"fast": 5, "slow": 20}' --out-of-sample

    输出 JSON：total_performance + accuracy_summary（V99）+ portfolio_trust（V103）
    + out_of_sample（V126，--out-of-sample 时）+ verdict 汇总。
    """
    import json

    from ..backtest.portfolio_engine import PortfolioBacktestEngine, StockData
    from ..backtest.strategies import get_registry
    from ..cli.conn import get_mac_client
    from ..cli.parsers import parse_adjust, parse_period, parse_stocks

    try:
        params: dict[str, Any] = json.loads(params_json) if params_json.strip() else {}
    except json.JSONDecodeError as exc:
        click.echo("错误: --params 不是合法 JSON: " + str(exc), err=True)
        raise SystemExit(1)

    try:
        entry = get_registry().get(strategy_name)
    except KeyError as exc:
        click.echo("错误: " + str(exc), err=True)
        raise SystemExit(1)
    strategy = entry.build(params)

    market_codes = parse_stocks(stocks)
    if not market_codes:
        click.echo('错误: 未解析到任何标的（格式如 "SZ 000001,SH 600519"）', err=True)
        raise SystemExit(1)

    # 取每只标的 K 线并组装 StockData
    stock_data_list: list[StockData] = []
    failures: list[str] = []
    with get_mac_client() as client:
        for market_int, code in market_codes:
            symbol = ("SZ" if market_int == 0 else ("SH" if market_int == 1 else "BJ")) + code
            try:
                df = client.get_stock_kline(
                    market_int,
                    code,
                    period=parse_period(period),
                    start=0,
                    count=count,
                    adjust=parse_adjust(adjust),
                )
                if df is None or len(df) < 30:
                    failures.append(symbol + "(行情不足)")
                    continue
                stock_data_list.append(
                    StockData(code=code, market=symbol[:2], df=df.reset_index(drop=True))
                )
            except Exception as exc:  # noqa: BLE001 — 单只失败跳过
                failures.append(symbol + "(" + str(exc) + ")")

    if not stock_data_list:
        click.echo("错误: 所有标的均未取到有效行情数据", err=True)
        raise SystemExit(1)

    engine = PortfolioBacktestEngine(
        strategy=strategy,
        stocks=stock_data_list,
        total_cash=cash,
        commission=commission,
        slippage=slippage,
    )
    result = engine.run()
    report = result.to_dict()
    report["failures"] = failures

    # V99: 组合级准确度聚合
    try:
        from ..backtest.signal_accuracy import aggregate_portfolio_accuracy

        individual = getattr(result, "individual_results", None)
        if individual:
            allocations = {str(k): float(v) for k, v in (result.equity_allocation or {}).items()}
            report["accuracy_summary"] = aggregate_portfolio_accuracy(individual, allocations)
    except Exception:
        pass

    # V103: 组合可信度
    try:
        from ..backtest.model_trust import compute_portfolio_trust

        report["portfolio_trust"] = compute_portfolio_trust(report.get("accuracy_summary"))
    except Exception:
        pass

    # V126: 组合级样本外验证
    if run_oos:
        try:
            from ..backtest.out_of_sample import compute_out_of_sample

            per_symbol: dict[str, Any] = {}
            degraded_symbols = 0
            n = len(stock_data_list)
            for sd in stock_data_list:
                symbol = sd.market + sd.code
                try:
                    oos = compute_out_of_sample(
                        sd.df,
                        lambda: entry.build(params),
                        cash=cash / max(n, 1),
                        commission=commission,
                        slippage=slippage,
                    )
                    per_symbol[symbol] = {
                        "degraded": oos.get("degraded", False),
                        "verdict": oos.get("verdict", ""),
                        "train_return": (oos.get("train") or {}).get("total_return"),
                        "test_return": (oos.get("test") or {}).get("total_return"),
                    }
                    if oos.get("degraded"):
                        degraded_symbols += 1
                except Exception:
                    per_symbol[symbol] = {"degraded": True, "verdict": "样本外验证失败"}
            if per_symbol:
                _trs = [(v.get("train_return") or 0.0) for v in per_symbol.values()]
                _tes = [(v.get("test_return") or 0.0) for v in per_symbol.values()]
                avg_train = sum(_trs) / len(_trs)
                avg_test = sum(_tes) / len(_tes)
                degraded = degraded_symbols >= len(per_symbol) * 0.5 or avg_test < avg_train * 0.5
                verdict = (
                    f"{len(per_symbol) - degraded_symbols}/{len(per_symbol)} 只样本外稳健；"
                    f"平均训练段 {avg_train:+.1%} → 样本外 {avg_test:+.1%}"
                )
                if degraded:
                    verdict += "。⚠ 组合样本外表现衰减，历史成绩需谨慎对待"
                report["out_of_sample"] = {
                    "symbols": len(per_symbol),
                    "degraded_symbols": degraded_symbols,
                    "avg_train_return": avg_train,
                    "avg_test_return": avg_test,
                    "degraded": degraded,
                    "verdict": verdict,
                    "per_symbol": per_symbol,
                }
        except Exception:
            pass

    # 汇总结论
    verdict_parts: list[str] = []
    mt = report.get("portfolio_trust") or {}
    if mt.get("grade"):
        trust_str = (
            "组合可信度 " + str(mt.get("grade")) + "（"
            + str(int(mt.get("score", 0))) + "/100）"
        )
        verdict_parts.append(trust_str)
    acc = report.get("accuracy_summary") or {}
    if acc.get("verdict"):
        verdict_parts.append(str(acc["verdict"]))
    oos = report.get("out_of_sample") or {}
    if oos.get("verdict"):
        verdict_parts.append(str(oos["verdict"]))
    report["verdict"] = "；".join(verdict_parts) if verdict_parts else "无验证结论"

    text = json.dumps(report, ensure_ascii=False, indent=2, default=str)
    if output_file:
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(text + "\n")
        click.echo("已写入 " + output_file)
    else:
        click.echo(text)
