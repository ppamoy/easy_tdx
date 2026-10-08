"""缠论因子 — 桥接 ChanlunAnalyser。

索引口径（2026 实测，已固化为本文件事实标准）
------------------------------------------
``FX.k.k_index`` / ``CLKline.k_index`` 是**原始 K 行号**（可直接当 ``df.iloc[i]``
用），不是合并后缠论 K 的序号。实测证据（tests/fixtures 五个 fixture，均为 160 根）：
合并后 ``cklines`` 只有 81~130 根，但笔端点 ``k_index`` 最大值达 **150~156**，
远大于任何一份的 ck 长度、且贴近 ``len(df)-1=159`` —— 所以它必然是原始行号。
另：逐端点核对 ``df.date[k_index] == FX.k.date`` 共 20/20 全部吻合。

注意不要用 ``FX.bar_index`` 代替：实测 chanlun_000333_daily 的 bi[1].end 上
``k_index=35`` 与自身日期 2025-03-20 对齐，而 ``bar_index=34`` 错了一根。

同理 ``MMD`` 没有 ``.type`` / ``.index``，正确路径是 ``mmd.mmd_type``
（``MMDType``，是 str Enum，``.value`` 形如 ``"1buy"``）与锚定 K 线
``mmd.bi.end.k.k_index``。这两个别名过去写成 ``getattr(mmd, "type", "")``，
配合 ``except Exception: pass`` 让 AttributeError 静默变成「永远零信号」。
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from easy_tdx.factor.base import Factor, register_factor

logger = logging.getLogger(__name__)

# 「数据本身算不出结构」的错误才允许降级成全 0；其余（属性写错/类型不对）必须抛出去。
# AttributeError/TypeError/KeyError 一律不放行：它们几乎必然是编程错误，而历史上的
# blanket `except Exception: pass` 正是把它们伪装成「缠论今天没信号」，让用户长期误判。
_DATA_ERRORS = (ValueError, IndexError, ZeroDivisionError, ArithmeticError)


def _direction_sign(direction: object) -> float | None:
    """把 Direction / "up" / "down" 归一成 +1.0 / -1.0；未知方向返回 None。"""
    raw = getattr(direction, "value", direction)
    if raw == "up":
        return 1.0
    if raw == "down":
        return -1.0
    return None


@register_factor
class ChanlunBiDir(Factor):
    name = "chanlun_bi_dir"
    category = "chanlun"
    description = "当前笔方向（+1=向上笔，-1=向下笔，0=无笔）"
    inputs = ("open", "high", "low", "close", "vol", "amount")

    def compute(self, df: pd.DataFrame) -> pd.Series:
        result = pd.Series(0.0, index=df.index, dtype=np.float64)

        try:
            from easy_tdx.chanlun.analyser import ChanlunAnalyser

            analyser = ChanlunAnalyser(frequency="DAILY")
            chanlun_result = analyser.process_klines(df)
            bis = chanlun_result.bis

            if not bis:
                return result

            n = len(df)
            for bi in bis:
                direction = _direction_sign(bi.direction)
                if direction is None:
                    logger.debug("chanlun_bi_dir: 未知笔方向 %r，跳过 bi[%s]", bi.direction, bi.index)
                    continue
                # k.k_index 已是原始行号（见模块 docstring 实测），闭区间 [start, end]
                lo = max(0, bi.start.k.k_index)
                hi = min(n, bi.end.k.k_index + 1)
                result.iloc[lo:hi] = direction

            # 最后一笔之后到序列末尾：不再有「已完成的新笔」，最近已知笔仍是它，
            # 故延续其方向到最后一格（等价于原实现里那句孤立的 result.iloc[-1] = direction，
            # 但这里是整段延续，不会出现「末尾 8 格为 0、只有最后 1 格有值」的裂缝）。
            tail = _direction_sign(bis[-1].direction)
            if tail is not None:
                result.iloc[max(0, bis[-1].end.k.k_index):] = tail

        except _DATA_ERRORS as exc:
            logger.warning("chanlun_bi_dir: 缠论计算失败，退化为全 0 序列: %s", exc)

        return result


@register_factor
class ChanlunMMD(Factor):
    name = "chanlun_mmd"
    category = "chanlun"
    description = "最近买卖点类型编码（正=买点，负=卖点，0=无信号）"
    inputs = ("open", "high", "low", "close", "vol", "amount")

    _MMD_MAP: dict[str, float] = {
        "1buy": 1.0,
        "2buy": 2.0,
        "3buy": 3.0,
        "l3buy": 3.0,
        "1sell": -1.0,
        "2sell": -2.0,
        "3sell": -3.0,
        "s3sell": -3.0,
    }

    def compute(self, df: pd.DataFrame) -> pd.Series:
        result = pd.Series(0.0, index=df.index, dtype=np.float64)

        try:
            from easy_tdx.chanlun.analyser import ChanlunAnalyser

            analyser = ChanlunAnalyser(frequency="DAILY")
            chanlun_result = analyser.process_klines(df)
            mmds = chanlun_result.mmds

            if not mmds:
                return result

            for mmd in mmds:
                if mmd.bi is None:
                    logger.debug("chanlun_mmd: 买卖点 %s 无锚定笔，跳过", mmd.mmd_type)
                    continue
                # MMDType 是 str Enum，用 .value 取 "1buy" 等字面量才能命中 _MMD_MAP；
                # 同理 getattr(..., "value", ...) 兜住直接存字符串的老路径。
                value = self._MMD_MAP.get(getattr(mmd.mmd_type, "value", mmd.mmd_type), 0.0)
                if value == 0.0:
                    logger.debug("chanlun_mmd: 未映射的买卖点类型 %s", mmd.mmd_type)
                    continue
                idx = mmd.bi.end.k.k_index
                if 0 <= idx < len(df):
                    result.iloc[idx] = value

        except _DATA_ERRORS as exc:
            logger.warning("chanlun_mmd: 缠论计算失败，退化为全 0 序列: %s", exc)

        return result
