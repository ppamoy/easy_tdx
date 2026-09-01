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

    click.echo(json.dumps(result_dict, ensure_ascii=False, indent=2, default=str))
