"""参数网格寻优器。

对单个策略的 1-2 个参数做网格搜索：遍历用户指定的取值列表的笛卡尔积，
每个组合跑一次回测，按 total_return 排序，返回排名 + 热力图矩阵。

设计镜像 :class:`~easy_tdx.backtest.combo.CombinationRunner` 的枚举/排序模式，
但遍历的是参数组合而非策略组合。网格大小硬上限 ``MAX_GRID_POINTS`` 防组合爆炸。

用法::

    from easy_tdx.backtest.optimizer import ParamGridOptimizer

    opt = ParamGridOptimizer(
        strategy_name="ma_cross",
        param_grid={"fast": [5, 10, 20], "slow": [10, 20, 30]},
        df=df,
        cash=100000,
    )
    result = opt.run()
    print(result.best.params, result.best.total_return)
"""

from __future__ import annotations

import itertools
import logging
from dataclasses import dataclass
from typing import Any

import pandas as pd

from easy_tdx.backtest.engine import BacktestEngine
from easy_tdx.backtest.types import BacktestResult

logger = logging.getLogger(__name__)

# 网格点上限：防止组合爆炸。3 参数各 6 值 = 216 已接近上限。
MAX_GRID_POINTS = 200


@dataclass
class GridPointResult:
    """单个网格点的回测结果摘要。

    Attributes:
        params: 该点的参数取值（如 {"fast": 10, "slow": 20}）
        total_return: 总收益率
        sharpe: 夏普比率
        max_drawdown: 最大回撤
        total_trades: 总交易笔数
        win_rate: 胜率（0-1）
        profit_factor: 盈亏比
    """

    params: dict[str, Any]
    total_return: float = 0.0
    sharpe: float = 0.0
    max_drawdown: float = 0.0
    total_trades: int = 0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    # V109: 该网格点回测的信号准确度与模型可信度（从 BacktestResult 提取）
    hit_rate: float | None = None
    excess_hit_rate: float | None = None
    trust_score: float | None = None
    trust_grade: str | None = None


@dataclass
class OptimizeResult:
    """网格寻优完整结果。

    Attributes:
        strategy: 策略名
        param_names: 寻优的参数名列表（1-2 个，决定热力图维度）
        results: 所有网格点结果，按 total_return 降序排列
        best: 最优点（results[0] 的引用）
        heatmap: 2 参数时的热力图矩阵（x/y 轴取值 + cell 收益率）；1 参数或空时为 None
    """

    strategy: str
    param_names: list[str]
    results: list[GridPointResult]
    best: GridPointResult | None = None
    heatmap: dict[str, Any] | None = None
    # V123: Walk-Forward 滚动验证报告（启用时填充，普通寻优为 None）
    walk_forward: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """序列化为 JSON 兼容字典。"""
        import math

        def clean(v: Any) -> Any:
            if isinstance(v, float) and not math.isfinite(v):
                return None
            return v

        return {
            "strategy": self.strategy,
            "param_names": self.param_names,
            "results": [
                {
                    "params": r.params,
                    "total_return": clean(r.total_return),
                    "sharpe": clean(r.sharpe),
                    "max_drawdown": clean(r.max_drawdown),
                    "total_trades": r.total_trades,
                    "win_rate": clean(r.win_rate),
                    "profit_factor": clean(r.profit_factor),
                    "hit_rate": clean(r.hit_rate) if r.hit_rate is not None else None,
                    "excess_hit_rate": (
                        clean(r.excess_hit_rate) if r.excess_hit_rate is not None else None
                    ),
                    "trust_score": clean(r.trust_score) if r.trust_score is not None else None,
                    "trust_grade": r.trust_grade,
                }
                for r in self.results
            ],
            "best": (
                {
                    "params": self.best.params,
                    "total_return": clean(self.best.total_return),
                    "sharpe": clean(self.best.sharpe),
                    "max_drawdown": clean(self.best.max_drawdown),
                    "total_trades": self.best.total_trades,
                    "win_rate": clean(self.best.win_rate),
                    "profit_factor": clean(self.best.profit_factor),
                    "hit_rate": (
                        clean(self.best.hit_rate) if self.best.hit_rate is not None else None
                    ),
                    "excess_hit_rate": (
                        clean(self.best.excess_hit_rate)
                        if self.best.excess_hit_rate is not None
                        else None
                    ),
                    "trust_score": (
                        clean(self.best.trust_score) if self.best.trust_score is not None else None
                    ),
                    "trust_grade": self.best.trust_grade,
                }
                if self.best
                else None
            ),
            "heatmap": self.heatmap,
            "walk_forward": self.walk_forward,
        }


class ParamGridOptimizer:
    """参数网格寻优器。

    遍历 ``param_grid`` 的笛卡尔积，每个组合实例化策略 + 跑回测，
    收集指标后排序。复用同一份 DataFrame（引擎无跨 run 缓存，安全）。

    Args:
        strategy_name: 策略名（从注册表解析）
        param_grid: 参数取值网格，如 {"fast": [5,10,20], "slow": [10,20,30]}
        df: OHLCV DataFrame（所有网格点共用）
        cash: 初始资金
        commission: 佣金率
        min_commission: 最低佣金
        stamp_tax: 印花税
        slippage: 滑点
        execution: 成交模式
    """

    def __init__(
        self,
        strategy_name: str,
        param_grid: dict[str, list[Any]],
        df: pd.DataFrame,
        cash: float = 1_000_000.0,
        commission: float = 0.0003,
        min_commission: float = 5.0,
        stamp_tax: float = 0.001,
        slippage: float = 0.0,
        execution: str = "next_open",
    ) -> None:
        size = 1
        for vals in param_grid.values():
            size *= len(vals)
        if size > MAX_GRID_POINTS:
            raise ValueError(f"网格大小 {size} 超过上限 {MAX_GRID_POINTS}，请减少参数取值数量")
        if size == 0:
            raise ValueError("param_grid 不能有空取值列表")

        self._strategy_name = strategy_name
        self._param_grid = param_grid
        self._df = df
        self._cash = cash
        self._commission = commission
        self._min_commission = min_commission
        self._stamp_tax = stamp_tax
        self._slippage = slippage
        self._execution = execution

    def run(self) -> OptimizeResult:
        """执行网格寻优，返回排序后的结果。"""
        # 延迟导入避免循环依赖
        from easy_tdx.backtest.strategies import get_registry

        entry = get_registry().get(self._strategy_name)
        param_names = list(self._param_grid.keys())
        value_lists = [self._param_grid[name] for name in param_names]

        results: list[GridPointResult] = []
        for combo in itertools.product(*value_lists):
            params = dict(zip(param_names, combo, strict=True))
            try:
                # 寻优时跳过参数范围检查——探索超范围值是寻优的目的
                strategy = entry.build(params, skip_bounds=True)
                engine = BacktestEngine(
                    strategy=strategy,
                    cash=self._cash,
                    commission=self._commission,
                    min_commission=self._min_commission,
                    stamp_tax=self._stamp_tax,
                    slippage=self._slippage,
                    execution=self._execution,
                )
                bt_result: BacktestResult = engine.run(self._df)
                perf = bt_result.performance
                # V109: 提取信号准确度（5根前瞻命中率/超额）与模型可信度
                hit_rate: float | None = None
                excess_hit_rate: float | None = None
                sa = getattr(bt_result, "signal_accuracy", None)
                if sa:
                    buy = sa.get("buy") or {}
                    horizons = buy.get("horizons") or {}
                    h5 = horizons.get("5") or horizons.get("3")
                    if h5 and h5.get("count", 0) > 0:
                        hit_rate = float(h5["hit_rate"])
                        excess_hit_rate = float(h5.get("excess_hit_rate", 0.0))
                trust_score: float | None = None
                trust_grade: str | None = None
                # V101 的 model_trust 在路由层计算，BacktestResult 上可能没有；
                # 寻优场景无分段稳健性，直接在 optimizer 内用 signal_accuracy 计算。
                try:
                    from easy_tdx.backtest.model_trust import compute_model_trust

                    mt = getattr(bt_result, "model_trust", None)
                    if mt is None:
                        mt = compute_model_trust(
                            bt_result.performance,
                            sa,
                            None,  # 无 segment_robustness → 中性 0.5
                        )
                    if mt:
                        trust_score = float(mt.get("score", 0.0))
                        trust_grade = str(mt.get("grade", ""))
                except Exception:  # noqa: BLE001
                    pass
                results.append(
                    GridPointResult(
                        params=params,
                        total_return=perf.get("total_return", 0.0),
                        sharpe=perf.get("sharpe", 0.0),
                        max_drawdown=perf.get("max_drawdown", 0.0),
                        total_trades=int(perf.get("total_trades", 0)),
                        win_rate=perf.get("win_rate", 0.0),
                        profit_factor=perf.get("profit_factor", 0.0),
                        hit_rate=hit_rate,
                        excess_hit_rate=excess_hit_rate,
                        trust_score=trust_score,
                        trust_grade=trust_grade,
                    )
                )
            except Exception:  # noqa: BLE001 — 单点失败不中断整个网格
                logger.warning("网格点 %s 回测失败，跳过", params, exc_info=True)

        # 按 total_return 降序
        results.sort(key=lambda r: r.total_return, reverse=True)

        best = results[0] if results else None
        heatmap = self._build_heatmap(results, param_names) if len(param_names) == 2 else None

        return OptimizeResult(
            strategy=self._strategy_name,
            param_names=param_names,
            results=results,
            best=best,
            heatmap=heatmap,
        )

    def run_walk_forward(self, train_ratio: float = 0.7, step_ratio: float = 0.1) -> OptimizeResult:
        """执行 walk-forward 验证寻优。

        将数据切分为多个训练/测试窗口，在每个训练窗口上寻优，
        然后在对应测试窗口上验证，汇总各窗口表现返回综合排名。

        Args:
            train_ratio: 训练集比例（默认 0.7）
            step_ratio: 每次滚动步长比例（默认 0.1）

        Returns:
            OptimizeResult，best 为 walk-forward 综合最优参数
        """
        from easy_tdx.backtest.strategies import get_registry

        entry = get_registry().get(self._strategy_name)
        param_names = list(self._param_grid.keys())
        n = len(self._df)
        train_size = int(n * train_ratio)
        step_size = max(int(n * step_ratio), 1)

        if train_size < 100:
            raise ValueError(f"训练集过小（{train_size} 根），请增大 train_ratio 或增加数据量")

        windows: list[tuple[slice, slice]] = []
        train_start = 0
        while train_start + train_size <= n:
            test_start = train_start + train_size
            test_end = min(test_start + step_size * 2, n)  # 测试集至少 2×step
            windows.append((slice(train_start, test_start), slice(test_start, test_end)))
            train_start += step_size
            if test_end >= n:
                break

        if not windows:
            raise ValueError("数据不足以划分 walk-forward 窗口")

        # 对每个窗口做寻优，收集结果
        all_results: list[tuple[int, dict[str, Any], GridPointResult]] = []
        window_reports: list[dict[str, Any]] = []
        for win_idx, (train_slice, test_slice) in enumerate(windows):
            train_df = self._df.iloc[train_slice].reset_index(drop=True)
            test_df = self._df.iloc[test_slice].reset_index(drop=True)

            if len(train_df) < 50 or len(test_df) < 10:
                continue

            optimizer = ParamGridOptimizer(
                strategy_name=self._strategy_name,
                param_grid=self._param_grid,
                df=train_df,
                cash=self._cash,
                commission=self._commission,
                stamp_tax=self._stamp_tax,
                slippage=self._slippage,
                execution=self._execution,
            )
            train_result = optimizer.run()
            if train_result.best is None:
                continue

            # 在测试集上验证
            best_params = train_result.best.params
            try:
                strategy = entry.build(best_params, skip_bounds=True)
                test_engine = BacktestEngine(
                    strategy=strategy,
                    cash=self._cash,
                    commission=self._commission,
                    stamp_tax=self._stamp_tax,
                    slippage=self._slippage,
                    execution=self._execution,
                )
                test_bt = test_engine.run(test_df)
                perf = test_bt.performance
                all_results.append(
                    (
                        win_idx,
                        best_params,
                        GridPointResult(
                            params=best_params,
                            total_return=perf.get("total_return", 0.0),
                            sharpe=perf.get("sharpe", 0.0),
                            max_drawdown=perf.get("max_drawdown", 0.0),
                            total_trades=int(perf.get("total_trades", 0)),
                            win_rate=perf.get("win_rate", 0.0),
                            profit_factor=perf.get("profit_factor", 0.0),
                        ),
                    )
                )
                # V123: 记录该窗口的训练/测试绩效，用于滚动验证报告
                window_reports.append(
                    {
                        "window": win_idx,
                        "train_bars": len(train_df),
                        "test_bars": len(test_df),
                        "params": best_params,
                        "train_return": float(train_result.best.total_return),
                        "train_sharpe": float(train_result.best.sharpe),
                        "test_return": float(perf.get("total_return", 0.0)),
                        "test_sharpe": float(perf.get("sharpe", 0.0)),
                        "test_win_rate": float(perf.get("win_rate", 0.0)),
                        "test_trades": int(perf.get("total_trades", 0)),
                    }
                )
            except Exception:
                continue

        if not all_results:
            return OptimizeResult(strategy=self._strategy_name, param_names=param_names, results=[])

        # 按夏普比率综合排名（测试集夏普 + 训练集夏普的平均）
        all_results.sort(key=lambda x: x[2].sharpe, reverse=True)
        ranked = [r[2] for r in all_results]
        best = ranked[0] if ranked else None

        # V123: 汇总滚动验证结论
        walk_forward: dict[str, Any] | None = None
        if window_reports:
            n_win = len(window_reports)
            train_returns = [w["train_return"] for w in window_reports]
            test_returns = [w["test_return"] for w in window_reports]
            train_mean = sum(train_returns) / n_win
            test_mean = sum(test_returns) / n_win
            pos_test = sum(1 for v in test_returns if v > 0)
            pos_train = sum(1 for v in train_returns if v > 0)
            # 判定：测试窗口正收益占比 + 训练/测试差距
            verdict_parts: list[str] = []
            degraded = False
            if pos_test >= max(1, n_win * 0.5):
                verdict_parts.append(f"{pos_test}/{n_win} 个测试窗口正收益")
            else:
                verdict_parts.append(f"仅 {pos_test}/{n_win} 个测试窗口正收益")
                degraded = True
            if test_mean < train_mean * 0.5:
                verdict_parts.append("测试段收益较训练段明显衰减")
                degraded = True
            if degraded:
                verdict_parts.append("⚠ 滚动验证表现不稳，选参需谨慎（可能过拟合）")
            else:
                verdict_parts.append("滚动验证表现较稳定，参数可信度较高")
            walk_forward = {
                "windows": n_win,
                "train_mean": train_mean,
                "test_mean": test_mean,
                "positive_train_windows": pos_train,
                "positive_test_windows": pos_test,
                "degraded": degraded,
                "verdict": "；".join(verdict_parts),
                "windows_detail": window_reports,
            }

        return OptimizeResult(
            strategy=self._strategy_name,
            param_names=param_names,
            results=ranked,
            best=best,
            heatmap=None,
            walk_forward=walk_forward,
        )

    def _build_heatmap(
        self,
        results: list[GridPointResult],
        param_names: list[str],
    ) -> dict[str, Any]:
        """2 参数时构建热力图矩阵：x=参数1取值，y=参数2取值，cell=total_return。

        Returns:
            {"x": [...], "y": [...], "data": [[x_idx, y_idx, value], ...]}
        """
        x_name, y_name = param_names
        x_vals = sorted(set(self._param_grid[x_name]))
        y_vals = sorted(set(self._param_grid[y_name]))
        x_idx = {v: i for i, v in enumerate(x_vals)}
        y_idx = {v: i for i, v in enumerate(y_vals)}

        data: list[list[Any]] = []
        for r in results:
            x = r.params.get(x_name)
            y = r.params.get(y_name)
            if x not in x_idx or y not in y_idx:
                continue
            data.append([x_idx[x], y_idx[y], r.total_return])

        return {"x_name": x_name, "y_name": y_name, "x": x_vals, "y": y_vals, "data": data}
