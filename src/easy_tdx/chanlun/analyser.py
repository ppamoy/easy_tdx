"""缠论分析器主入口。

ChanlunAnalyser 接收 easy_tdx 的 K 线 DataFrame，
内部执行完整的缠论计算管道：
K线合并 → 分型识别 → 笔计算 → 中枢计算 → 线段 → 买卖点 → 背驰。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pandas as pd

from easy_tdx.chanlun.beichi import check_bi_beichi  # noqa: F401
from easy_tdx.chanlun.bi import find_bis
from easy_tdx.chanlun.config import ChanlunConfig
from easy_tdx.chanlun.fractal import find_fractals
from easy_tdx.chanlun.kline_merge import merge_klines
from easy_tdx.chanlun.macd import calc_macd  # noqa: F401
from easy_tdx.chanlun.mmd import find_mmds_v44  # noqa: F401
from easy_tdx.chanlun.types import BC, BI, FX, MMD, XD, ZS, CLKline, Kline
from easy_tdx.chanlun.xd import find_xds  # noqa: F401
from easy_tdx.MyTT import BOLL
from easy_tdx.chanlun.zs import find_zss


def _df_to_klines(df: pd.DataFrame) -> list[Kline]:
    """将 easy_tdx K 线 DataFrame 转为缠论 Kline 列表。

    期望 DataFrame 包含列：datetime, open, close, high, low, vol
    """
    klines: list[Kline] = []
    for i, row in enumerate(df.itertuples()):
        dt = getattr(row, "datetime", None) or getattr(row, "date", None)
        if dt is None:
            continue
        row_any: Any = row  # avoid pandas-stubs vs bare pandas type mismatch
        vol = getattr(row, "vol", 0.0) or 0.0
        klines.append(
            Kline(
                index=i,
                date=dt,
                open=float(row_any.open),
                close=float(row_any.close),
                high=float(row_any.high),
                low=float(row_any.low),
                amount=float(vol),
            )
        )
    return klines


@dataclass
class ChanlunResult:
    """缠论分析结果。"""

    code: str = ""
    frequency: str = ""
    klines: list[Kline] = field(default_factory=list)
    cklines: list[CLKline] = field(default_factory=list)
    fractals: list[FX] = field(default_factory=list)
    bis: list[BI] = field(default_factory=list)
    zss: list[ZS] = field(default_factory=list)
    xds: list[XD] = field(default_factory=list)
    mmds: list[MMD] = field(default_factory=list)
    bcs: list[BC] = field(default_factory=list)
    macd: dict[str, list[float]] = field(default_factory=dict)
    boll: Any = None  # BOLLResult or None

    def _fmt_dt(self, dt: datetime) -> str:
        """按 frequency 自适应格式化日期。

        分钟级别（1/5/15/30/60min）输出完整时分 YYYY-MM-DD HH:MM，
        日/周/月/年级别只输出日期 YYYY-MM-DD（无多余 00:00）。
        frequency 来自 CLI 原始值（如 5MIN/30MIN）或 Web 映射值（5min/30min），
        统一转小写后判断是否含 'min'。
        """
        fmt = "%Y-%m-%d %H:%M" if "min" in self.frequency.lower() else "%Y-%m-%d"
        return dt.strftime(fmt)

    def to_dict(self) -> dict[str, Any]:
        """将结果转为可序列化的字典（用于 JSON 输出）。"""
        return {
            "code": self.code,
            "frequency": self.frequency,
            "kline_count": len(self.klines),
            "ckline_count": len(self.cklines),
            "fractal_count": len(self.fractals),
            "bi_count": len(self.bis),
            "zs_count": len(self.zss),
            "xd_count": len(self.xds),
            "mmd_count": len(self.mmds),
            "bc_count": len(self.bcs),
            "bis": [
                {
                    "index": bi.index,
                    "direction": bi.direction.value,
                    "start_date": self._fmt_dt(bi.start.k.date),
                    "end_date": self._fmt_dt(bi.end.k.date),
                    "high": round(bi.high, 2),
                    "low": round(bi.low, 2),
                    "done": bi.is_done(),
                }
                for bi in self.bis
            ],
            "zss": [
                {
                    "index": zs.index,
                    "zg": round(zs.zg, 2),
                    "zd": round(zs.zd, 2),
                    "gg": round(zs.gg, 2),
                    "dd": round(zs.dd, 2),
                    "line_count": zs.line_count,
                    "start_date": self._fmt_dt(zs.start.k.date) if zs.start else None,
                    "end_date": self._fmt_dt(zs.end.k.date) if zs.end else None,
                    "done": zs.done,
                }
                for zs in self.zss
            ],
            "xds": [
                {
                    "index": xd.index,
                    "direction": xd.direction.value,
                    "start_date": self._fmt_dt(xd.start.k.date),
                    "end_date": self._fmt_dt(xd.end.k.date),
                    "high": round(xd.high, 2),
                    "low": round(xd.low, 2),
                }
                for xd in self.xds
            ],
            "mmds": [
                {
                    "type": mmd.mmd_type.value,
                    "date": self._fmt_dt(mmd.bi.end.k.date) if mmd.bi else None,
                    "msg": mmd.msg,
                    "confidence": round(mmd.confidence, 2),
                    "quality": {
                        "grade": mmd.quality.grade if mmd.quality else None,
                        "score": mmd.quality.score if mmd.quality else None,
                        "reasons": mmd.quality.reasons if mmd.quality else None,
                    } if mmd.quality else None,
                    # V79 缠论增强条件（条件248-251）
                    "v79_fractal_stability": getattr(mmd, "_fractal_stability_validation_v79", None),
                    "v79_distance_safety": getattr(mmd, "_mmd_distance_safety_v79", None),
                    "v79_multi_level_consistency": getattr(mmd, "_multi_level_structure_consistency_v79", None),
                    "v79_momentum_continuity": getattr(mmd, "_price_momentum_continuity_v79", None),
                    # V80 缠论增强条件（条件252-255）
                    "v80_zhongshu_distance": getattr(mmd, "_mmd_zhongshu_distance_v80", None),
                    "v80_volume_confirmation": getattr(mmd, "_volume_confirmation_v80", None),
                    "v80_ma_alignment": getattr(mmd, "_ma_alignment_strength_v80", None),
                    "v80_risk_reward": getattr(mmd, "_dynamic_risk_reward_v80", None),
                    # V81 缠论增强条件（条件256-259）
                    "v81_volatility_regime": getattr(mmd, "_volatility_regime_transition_v81", None),
                    "v81_support_resistance": getattr(mmd, "_support_resistance_strength_v81", None),
                    "v81_energy_distribution": getattr(mmd, "_volume_price_energy_distribution_v81", None),
                    "v81_execution_window": getattr(mmd, "_signal_execution_window_v81", None),
                    # V82 缠论增强条件（条件260-263）
                    "v82_age_decay": getattr(mmd, "_mmd_age_decay_v82", None),
                    "v82_breakout_retest": getattr(mmd, "_breakout_retest_confirm_v82", None),
                    "v82_macd_resonance": getattr(mmd, "_macd_multi_tf_resonance_v82", None),
                    "v82_volatility_compression": getattr(mmd, "_volatility_compression_breakout_v82", None),
                }
                for mmd in self.mmds
            ],
            "bcs": [
                {
                    "type": bc.bc_type.value,
                    "bc": bc.bc,
                    "curr_date": self._fmt_dt(bc.curr.end.k.date) if bc.curr else None,
                    "prev_date": self._fmt_dt(bc.prev.end.k.date) if bc.prev else None,
                    "msg": bc.msg,
                }
                for bc in self.bcs
            ],
        }


class ChanlunAnalyser:
    """缠论分析器。

    接收 easy_tdx K 线 DataFrame，执行缠论计算管道。

    用法：
        analyser = ChanlunAnalyser("SZ000001", "DAILY")
        analyser.process_klines(df)
        result = analyser.result
    """

    def __init__(
        self,
        code: str = "",
        frequency: str = "",
        config: ChanlunConfig | None = None,
    ) -> None:
        self._code = code
        self._frequency = frequency
        self._config = config or ChanlunConfig()
        self._result = ChanlunResult(
            code=code,
            frequency=frequency,
        )
        self._prev_df: pd.DataFrame | None = None

    @property
    def config(self) -> ChanlunConfig:
        return self._config

    @property
    def result(self) -> ChanlunResult:
        return self._result

    def process_klines(self, df: pd.DataFrame) -> ChanlunResult:
        """处理 K 线 DataFrame，执行缠论计算管道。

        Args:
            df: easy_tdx 返回的 K 线 DataFrame

        Returns:
            ChanlunResult 包含所有缠论计算结果
        """
        self._prev_df = df.copy()
        # Step 1: DataFrame → Kline 列表
        klines = _df_to_klines(df)
        self._result.klines = klines

        if not klines:
            return self._result

        # Step 2: K线包含处理
        cklines = merge_klines(klines)
        self._result.cklines = cklines

        # Step 3: 分型识别
        fractals = find_fractals(cklines, self._config)
        self._result.fractals = fractals

        # Step 4: 笔计算
        bis = find_bis(fractals, self._config)
        self._result.bis = bis

        # Step 5: 中枢计算
        zss = find_zss(bis, self._config)
        self._result.zss = zss

        # Step 6: MACD 计算
        closes = [k.close for k in klines]
        self._result.macd = calc_macd(
            closes, self._config.macd_fast, self._config.macd_slow, self._config.macd_signal
        )

        # Step 7: 线段计算
        xds = find_xds(bis, self._config)
        self._result.xds = xds

        # Step 7.5: BOLL 指标计算
        if len(closes) >= 20:
            from easy_tdx.chanlun.types import BOLLResult
            _upper, _mid, _lower = BOLL(closes, N=20, P=2)
            _width = [(_upper[i] - _lower[i]) / _mid[i] if _mid[i] > 0 else 0 for i in range(len(_upper))]
            _pb = []
            for i in range(len(closes)):
                ub = _upper[i]
                lb = _lower[i]
                _pb.append((closes[i] - lb) / (ub - lb) if (ub - lb) > 0 else 0.5)
            self._result.boll = BOLLResult(
                upper=_upper, mid=_mid, lower=_lower,
                width=_width, percent_b=_pb,
            )

        # Step 8: 买卖点识别（传入收盘价用于MACD力度计算）
        # 提取成交量序列
        volumes = [k.amount for k in klines]
        # V5: 计算波动率用于动态阈值
        from easy_tdx.chanlun.mmd import _calc_atr_volatility
        volatility = _calc_atr_volatility(closes) if len(closes) > 0 else None
        # V12: 传递highs/lows用于真实ADX计算
        highs = [k.high for k in klines]
        lows = [k.low for k in klines]
        mmds = find_mmds_v44(bis, zss, closes=closes, config=self._config, volumes=volumes, macd_data=self._result.macd, volatility=volatility, highs=highs, lows=lows)
        self._result.mmds = mmds

        # Step 9: 背驰判断（传入收盘价用于MACD面积计算）
        bcs = check_bi_beichi(bis, zss, closes=closes, config=self._config)
        self._result.bcs = bcs

        return self._result

    def append_klines(self, df_new: pd.DataFrame) -> ChanlunResult:
        """增量追加 K 线数据并重新计算。

        将新数据追加到之前处理过的 DataFrame 后面，
        然后在完整数据上重新执行缠论计算管道。

        相比手动拼接 + process_klines 的优势：
        - API 更简洁，无需用户管理 DataFrame 拼接
        - 未来可优化为只重新计算受影响的部分

        Args:
            df_new: 新增的 K 线 DataFrame

        Returns:
            更新后的 ChanlunResult

        Raises:
            RuntimeError: 如果之前没有调用过 process_klines
        """
        if self._prev_df is None:
            msg = "请先调用 process_klines() 初始化，再使用 append_klines()"
            raise RuntimeError(msg)

        # 拼接旧数据 + 新数据
        combined = pd.concat([self._prev_df, df_new], ignore_index=True)

        # 去重（防止重复追加）
        if "datetime" in combined.columns:
            combined = combined.drop_duplicates(subset=["datetime"], keep="last")
            combined = combined.reset_index(drop=True)

        return self.process_klines(combined)

    def get_bis(self) -> list[BI]:
        return self._result.bis

    def get_zss(self) -> list[ZS]:
        return self._result.zss

    def get_fxs(self) -> list[FX]:
        return self._result.fractals

    def get_klines(self) -> list[Kline]:
        return self._result.klines

    def get_cklines(self) -> list[CLKline]:
        return self._result.cklines
