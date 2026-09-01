"""CLI 策略库一键重验（V213）：对策略库保存的单标/组合策略用原标的重新回测，刷新验证结论。

与 Web 端 V209/V211 的「↻ 重验」对齐，方便脚本/Agent 批量刷新已保存策略的
准确度 / 可信度 / 样本外结论。
"""

from __future__ import annotations

from typing import Any

import click


@click.command("reverify")
@click.option("--ids", "only_ids", default=None, help="逗号分隔的策略 id（默认全部）")
@click.option("--count", default=500, type=int, help="每只标的 K线数量")
@click.option("--period", default="DAILY", help="K线周期")
@click.option("--adjust", default="NONE", help="复权: NONE/QFQ/HFQ")
@click.option("--cash", default=1_000_000.0, type=float, help="单标资金/组合总资金")
@click.option("--commission", default=0.0003, type=float, help="佣金率")
@click.option("--slippage", default=0.0, type=float, help="滑点")
def reverify(
    only_ids: str | None,
    count: int,
    period: str,
    adjust: str,
    cash: float,
    commission: float,
    slippage: float,
) -> None:
    """策略库一键重验：逐条读取保存的策略，用原标的重新回测并刷新快照。

    单标策略（kind=single）：对 context.symbol 重新回测（含样本外），刷新
    performance/accuracy/robustness/trust/out_of_sample，标记 source=reverify。

    组合策略（kind=portfolio）：对 context.stocks 重跑组合回测（含 V126 组合样本外），
    刷新 total_performance/accuracy_summary/portfolio_trust/out_of_sample。

    输出：每条的 id/名称/类型/状态 与刷新的关键字段。
    """
    import json

    from ..web.strategy_store import get_store

    store = get_store()
    all_records = store.list_all()
    if only_ids:
        wanted = {x.strip() for x in only_ids.split(",") if x.strip()}
        all_records = [r for r in all_records if r.id in wanted]
    if not all_records:
        click.echo("没有可重验的策略")
        raise SystemExit(1)

    results: list[dict[str, Any]] = []
    failures: list[str] = []
    for rec in all_records:
        if rec.kind not in ("single", "portfolio", "multi"):
            failures.append(rec.id + "(" + rec.kind + " 类型暂不支持)")
            continue
        try:
            snapshot = _reverify_one(store, rec, count, period, adjust, cash, commission, slippage)
            store.update_snapshot(rec.id, snapshot)
            results.append(
                {
                    "id": rec.id,
                    "name": rec.name,
                    "kind": rec.kind,
                    "status": "ok",
                    "total_return": snapshot.get("total_return"),
                    "trust_grade": (snapshot.get("trust") or {}).get("grade"),
                    "oos_degraded": (snapshot.get("out_of_sample") or {}).get("degraded"),
                }
            )
        except Exception as exc:  # noqa: BLE001 — 单条失败不中断整体
            failures.append(rec.id + "(" + str(exc) + ")")
            results.append(
                {"id": rec.id, "name": rec.name, "kind": rec.kind,
                 "status": "error", "error": str(exc)}
            )

    text = json.dumps(
        {"total": len(all_records), "ok": sum(1 for r in results if r.get("status") == "ok"),
         "results": results, "failures": failures},
        ensure_ascii=False,
        indent=2,
        default=str,
    )
    click.echo(text)


def _reverify_one(
    store: Any,
    rec: Any,
    count: int,
    period: str,
    adjust: str,
    cash: float,
    commission: float,
    slippage: float,
) -> dict[str, Any]:
    """对单条策略重新回测并构造新快照。"""
    from ..backtest.strategies import get_registry

    # multi 类型：策略在 items 里各自解析，rec.strategy 只是占位（"multi"）
    ctx = rec.context or {}
    cfg = rec.trade_config or {}
    exec_mode = str(cfg.get("execution") or "next_open")
    today = __import__("datetime").date.today().isoformat()

    strategy: Any = None
    if rec.kind != "multi":
        try:
            entry = get_registry().get(rec.strategy)
        except KeyError as exc:
            raise ValueError("策略未注册: " + rec.strategy) from exc
        strategy = entry.build(rec.params or {})

    if rec.kind == "single":
        return _reverify_single(
            strategy, ctx, count, period, adjust, cash, commission, slippage, exec_mode, today
        )
    if rec.kind == "multi":
        return _reverify_multi(
            strategy, ctx, count, period, adjust, cash, commission, slippage, exec_mode, today
        )
    return _reverify_portfolio(
        strategy, ctx, count, period, adjust, cash, commission, slippage, exec_mode, today
    )


def _reverify_single(strategy: Any, ctx: dict[str, Any], count: int, period: str, adjust: str,
    cash: float, commission: float, slippage: float, exec_mode: str, today: str,
) -> dict[str, Any]:
    """单标重验：对 context.symbol 重新回测（含样本外）。"""
    from ..backtest import BacktestEngine
    from ..cli.conn import get_mac_client
    from ..cli.parsers import parse_adjust, parse_period

    sym = str(ctx.get("symbol") or "")
    sep = sym.find(":")
    if sep < 1:
        raise ValueError("缺少 symbol 上下文")
    market = sym[:sep]
    code = sym[sep + 1 :]
    market_int = {"SZ": 0, "SH": 1, "BJ": 2}.get(market)
    if market_int is None:
        raise ValueError("未知市场: " + market)

    with get_mac_client() as client:
        df = client.get_stock_kline(
            market_int, code, period=parse_period(period), start=0, count=count,
            adjust=parse_adjust(adjust),
        )
        if df is None or len(df) < 30:
            raise ValueError("行情不足")
        engine = BacktestEngine(
            strategy=strategy, cash=cash, commission=commission, slippage=slippage,
            execution=exec_mode,
        )
        result = engine.run(df.reset_index(drop=True))
        bp = result.performance
        sa = result.signal_accuracy or {}
        buy = sa.get("buy") or {}
        h5 = (buy.get("horizons") or {}).get("5") or {}
        try:
            from ..backtest.model_trust import compute_model_trust

            mt = compute_model_trust(bp, sa, None)
        except Exception:  # noqa: BLE001
            mt = {}
        try:
            from ..backtest.out_of_sample import compute_out_of_sample

            oos = compute_out_of_sample(
                df.reset_index(drop=True), lambda: strategy, cash=cash,
                commission=commission, slippage=slippage,
            )
        except Exception:  # noqa: BLE001
            oos = {}
        # V97: 分段稳健性单独计算（BacktestResult 不内置该字段）
        try:
            from ..backtest.robustness import compute_segment_robustness

            robust = compute_segment_robustness(
                df.reset_index(drop=True),
                lambda: strategy,
                segments=3,
                cash=cash,
                commission=commission,
                slippage=slippage,
                execution=exec_mode,
            )
        except Exception:  # noqa: BLE001
            robust = {}
        return {
            "total_return": bp.get("total_return"),
            "annual_return": bp.get("annual_return"),
            "max_drawdown": bp.get("max_drawdown"),
            "sharpe": bp.get("sharpe"),
            "win_rate": bp.get("win_rate"),
            "trades_count": bp.get("total_trades"),
            "accuracy": {
                "hit_rate": h5.get("hit_rate"),
                "excess_hit_rate": h5.get("excess_hit_rate"),
                "verdict": sa.get("verdict", ""),
            },
            "robustness": {
                "overfit_likely": robust.get("overfit_likely", False),
                "verdict": robust.get("verdict", ""),
            },
            "trust": {
                "score": mt.get("score"),
                "grade": mt.get("grade", ""),
                "verdict": mt.get("verdict", ""),
            },
            "out_of_sample": {
                "degraded": oos.get("degraded", False),
                "verdict": oos.get("verdict", ""),
                "train_return": (oos.get("train") or {}).get("total_return"),
                "test_return": (oos.get("test") or {}).get("total_return"),
            },
            "source": "reverify",
            "reverified_at": today,
        }


def _reverify_portfolio(strategy: Any, ctx: dict[str, Any], count: int, period: str, adjust: str,
       cash: float, commission: float, slippage: float, exec_mode: str, today: str,
) -> dict[str, Any]:
    """组合重验：对 context.stocks 重跑组合回测（含 V126 组合样本外）。"""
    from ..backtest.portfolio_engine import PortfolioBacktestEngine, StockData
    from ..cli.conn import get_mac_client
    from ..cli.parsers import parse_adjust, parse_period

    stocks = [s for s in (ctx.get("stocks") or []) if isinstance(s, str)]
    if not stocks:
        raise ValueError("缺少 context.stocks")
    stock_data_list: list[StockData] = []
    with get_mac_client() as client:
        for sym in stocks:
            sep = sym.find(":")
            if sep < 1:
                continue
            market = sym[:sep]
            code = sym[sep + 1 :]
            market_int = {"SZ": 0, "SH": 1, "BJ": 2}.get(market)
            if market_int is None:
                continue
            df = client.get_stock_kline(
                market_int, code, period=parse_period(period), start=0, count=count,
                adjust=parse_adjust(adjust),
            )
            if df is not None and len(df) >= 30:
                stock_data_list.append(
                    StockData(code=code, market=market, df=df.reset_index(drop=True))
                )
    if not stock_data_list:
        raise ValueError("所有组合标的行情获取失败")

    engine = PortfolioBacktestEngine(
        strategy=strategy, stocks=stock_data_list, total_cash=cash,
        commission=commission, slippage=slippage, execution=exec_mode,
    )
    result = engine.run()
    tp = result.total_performance
    report: dict[str, Any] = {
        "total_return": getattr(tp, "total_return", None),
        "annual_return": getattr(tp, "annual_return", None),
        "total_stocks": getattr(tp, "total_stocks", None),
    }
    try:
        from ..backtest.signal_accuracy import aggregate_portfolio_accuracy

        individual = getattr(result, "individual_results", None)
        if individual:
            allocations = {str(k): float(v) for k, v in (result.equity_allocation or {}).items()}
            acc = aggregate_portfolio_accuracy(individual, allocations)
            report["accuracy"] = {
                "hit_rate": (acc.get("portfolio") or {}).get("avg_hit_rate"),
                "excess_hit_rate": (acc.get("portfolio") or {}).get("avg_excess_hit_rate"),
                "verdict": acc.get("verdict", ""),
            }
    except Exception:  # noqa: BLE001
        pass
    try:
        from ..backtest.model_trust import compute_portfolio_trust

        pt = compute_portfolio_trust(report.get("accuracy"))
        report["trust"] = {
            "score": pt.get("score"),
            "grade": pt.get("grade", ""),
            "verdict": pt.get("verdict", ""),
        }
    except Exception:  # noqa: BLE001
        pass
    try:
        from ..backtest.out_of_sample import compute_out_of_sample

        per_symbol: dict[str, Any] = {}
        degraded = 0
        n = len(stock_data_list)
        for sd in stock_data_list:
            try:
                o = compute_out_of_sample(
                    sd.df, lambda: strategy, cash=cash / max(n, 1),
                    commission=commission, slippage=slippage,
                )
                per_symbol[sd.market + sd.code] = {
                    "degraded": o.get("degraded", False),
                    "verdict": o.get("verdict", ""),
                    "train_return": (o.get("train") or {}).get("total_return"),
                    "test_return": (o.get("test") or {}).get("total_return"),
                }
                if o.get("degraded"):
                    degraded += 1
            except Exception:  # noqa: BLE001
                per_symbol[sd.market + sd.code] = {"degraded": True, "verdict": "失败"}
        _tr = [(v.get("train_return") or 0.0) for v in per_symbol.values()]
        _te = [(v.get("test_return") or 0.0) for v in per_symbol.values()]
        avg_train = sum(_tr) / max(len(_tr), 1)
        avg_test = sum(_te) / max(len(_te), 1)
        report["out_of_sample"] = {
            "degraded": degraded >= len(per_symbol) * 0.5 or avg_test < avg_train * 0.5,
            "verdict": (
                f"{len(per_symbol) - degraded}/{len(per_symbol)} 只样本外稳健；"
                f"平均训练段 {avg_train:+.1%} → 样本外 {avg_test:+.1%}"
            ),
            "avg_train_return": avg_train,
            "avg_test_return": avg_test,
        }
    except Exception:  # noqa: BLE001
        pass
    report["source"] = "reverify"
    report["reverified_at"] = today
    return report




def _reverify_multi(
    strategy: Any, ctx: dict[str, Any], count: int, period: str, adjust: str,
    cash: float, commission: float, slippage: float, exec_mode: str, today: str,
) -> dict[str, Any]:
    """多策略组合重验（V229）：对 context.items 各策略在其原标的上重跑，刷新组合快照。"""
    from ..backtest.multi_strategy_engine import MultiStrategyEngine, StrategySlot
    from ..backtest.strategies import get_registry
    from ..cli.conn import get_mac_client
    from ..cli.parsers import parse_adjust, parse_period

    items = [it for it in (ctx.get("items") or []) if isinstance(it, dict)]
    items = [
        it for it in items
        if it.get("strategy") and it.get("symbol") and ":" in str(it.get("symbol", ""))
    ]
    if not items:
        raise ValueError("缺少 context.items")

    slots: list[StrategySlot] = []
    failures: list[str] = []
    with get_mac_client() as client:
        for it in items:
            sym = str(it["symbol"])
            sep = sym.find(":")
            market = sym[:sep]
            code = sym[sep + 1 :]
            market_int = {"SZ": 0, "SH": 1, "BJ": 2}.get(market)
            if market_int is None:
                failures.append(sym + "(未知市场)")
                continue
            try:
                entry = get_registry().get(str(it["strategy"]))
            except KeyError:
                failures.append(sym + "(策略未注册)")
                continue
            s_params = it.get("params") or {}
            df = client.get_stock_kline(
                market_int, code, period=parse_period(period), start=0, count=count,
                adjust=parse_adjust(adjust),
            )
            if df is None or len(df) < 30:
                failures.append(sym + "(行情不足)")
                continue
            strategy_obj = entry.build(dict(s_params))
            slots.append(
                StrategySlot(
                    label=str(it.get("strategy_label") or it["strategy"]),
                    symbol=sym,
                    strategy=strategy_obj,
                    df=df.reset_index(drop=True),
                )
            )
    if not slots:
        raise ValueError("所有策略槽位行情/注册失败")

    engine = MultiStrategyEngine(
        strategies=slots,
        total_cash=cash,
        commission=commission,
        slippage=slippage,
        execution=exec_mode,
    )
    result = engine.run()
    tp = result.total_performance
    report: dict[str, Any] = {
        "total_return": tp.get("total_return"),
        "annual_return": tp.get("annual_return"),
        "total_stocks": tp.get("total_stocks"),
        "total_cash": tp.get("total_cash"),
    }
    try:
        from ..backtest.signal_accuracy import aggregate_portfolio_accuracy

        individual = getattr(result, "individual_results", None)
        if individual:
            allocations = {str(k): float(v) for k, v in (result.equity_allocation or {}).items()}
            acc = aggregate_portfolio_accuracy(individual, allocations)
            report["accuracy"] = {
                "hit_rate": (acc.get("portfolio") or {}).get("avg_hit_rate"),
                "excess_hit_rate": (acc.get("portfolio") or {}).get("avg_excess_hit_rate"),
                "verdict": acc.get("verdict", ""),
            }
    except Exception:  # noqa: BLE001
        pass
    try:
        from ..backtest.model_trust import compute_portfolio_trust

        pt = compute_portfolio_trust(report.get("accuracy"))
        report["trust"] = {
            "score": pt.get("score"),
            "grade": pt.get("grade", ""),
            "verdict": pt.get("verdict", ""),
        }
    except Exception:  # noqa: BLE001
        pass
    try:
        from ..backtest.out_of_sample import compute_out_of_sample

        per_symbol: dict[str, Any] = {}
        degraded = 0
        n = len(slots)
        for sd in slots:
            try:
                o = compute_out_of_sample(
                    sd.df, lambda: sd.strategy, cash=cash / max(n, 1),
                    commission=commission, slippage=slippage,
                )
                per_symbol[sd.symbol] = {
                    "degraded": o.get("degraded", False),
                    "verdict": o.get("verdict", ""),
                    "train_return": (o.get("train") or {}).get("total_return"),
                    "test_return": (o.get("test") or {}).get("total_return"),
                }
                if o.get("degraded"):
                    degraded += 1
            except Exception:  # noqa: BLE001
                per_symbol[sd.symbol] = {"degraded": True, "verdict": "失败"}
        _tr = [(v.get("train_return") or 0.0) for v in per_symbol.values()]
        _te = [(v.get("test_return") or 0.0) for v in per_symbol.values()]
        avg_train = sum(_tr) / max(len(_tr), 1)
        avg_test = sum(_te) / max(len(_te), 1)
        report["out_of_sample"] = {
            "degraded": degraded >= len(per_symbol) * 0.5 or avg_test < avg_train * 0.5,
            "verdict": (
                f"{len(per_symbol) - degraded}/{len(per_symbol)} 只样本外稳健；"
                f"平均训练段 {avg_train:+.1%} → 样本外 {avg_test:+.1%}"
            ),
            "avg_train_return": avg_train,
            "avg_test_return": avg_test,
        }
    except Exception:  # noqa: BLE001
        pass
    report["source"] = "reverify"
    report["reverified_at"] = today
    return report
