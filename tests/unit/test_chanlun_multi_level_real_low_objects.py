"""V731：query_low_level_qs 必须暴露**真实**低级别笔/中枢对象。

背景（实测确认的"零件齐全但没接上"）：

- `query_low_level_qs` 内部确实筛选出了真实低级别 `low_bis` / `low_zss`
  （按高级别笔的时间窗口从**真实行情**分析结果里取），但**只返回计数**
  （`bi_count` / `zs_count`）和若干布尔，对象列表作为局部变量被丢弃。
- 而 `compute_qujiantao_cross_period` 做逐信号确认时**需要对象列表**
  （`bis_low` / `zss_low`），不是计数。
- 结果：跨周期区间套拿不到真实低级别结构，只好去用 `level_synth` 的
  **合成**数据（该模块自述「只是近似，不是真实 Tick」），于是自称"真区间套"
  的标签建立在近似数据上（见 test_qujiantao_synthetic_contract）。

也就是说：**真区间套的两个零件都已存在**——
  真实低级别数据（本函数） + 逐信号原文语义确认（compute_qujiantao_cross_period），
只是前者把对象丢了，两者没接上。

修复（V731）：返回里补 `bis` / `zss` 字段暴露真实对象。新增字段，既有
调用方（cli / router / 既有测试）都按 key 取值，行为不变。
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from easy_tdx.chanlun import ChanlunAnalyser
from easy_tdx.chanlun.config import ChanlunConfig
from easy_tdx.chanlun.multi_level import MultiLevelAnalyser
from easy_tdx.chanlun.types import BI, ZS

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures"


def _daily_df() -> pd.DataFrame:
    rows = json.loads((FIXTURE_DIR / "chanlun_000001_daily.json").read_text(encoding="utf-8"))
    return pd.DataFrame(rows)


def _mla_with_both_levels() -> tuple[MultiLevelAnalyser, object]:
    high_analyser = ChanlunAnalyser(code="000001", frequency="daily", config=ChanlunConfig(zs_from_xd=False))
    low_analyser = ChanlunAnalyser(code="000001", frequency="daily", config=ChanlunConfig(zs_from_xd=False))
    high_result = high_analyser.process_klines(_daily_df())
    low_analyser.process_klines(_daily_df())
    mla = MultiLevelAnalyser()
    mla.add_level("high", high_analyser)
    mla.add_level("low", low_analyser)
    return mla, high_result


class TestRealLowLevelObjectsExposed:
    """真实低级别对象必须可用，而不只是计数。"""

    def test_returns_real_bis_and_zss(self) -> None:
        mla, high_result = _mla_with_both_levels()
        qs = mla.query_low_level_qs("high", "low", high_result.bis[-1])
        assert "bis" in qs, "必须暴露真实低级别笔列表"
        assert "zss" in qs, "必须暴露真实低级别中枢列表"
        assert isinstance(qs["bis"], list)
        assert isinstance(qs["zss"], list)

    def test_objects_are_typed_not_counts(self) -> None:
        """反向锁定：不能退化成数字/布尔（那正是修复前的形态）。"""
        mla, high_result = _mla_with_both_levels()
        qs = mla.query_low_level_qs("high", "low", high_result.bis[-1])
        for bi in qs["bis"]:
            assert isinstance(bi, BI), f"期望 BI 对象，实际 {type(bi)}"
        for zs in qs["zss"]:
            assert isinstance(zs, ZS), f"期望 ZS 对象，实际 {type(zs)}"

    def test_objects_consistent_with_counts(self) -> None:
        """对象列表必须与计数一致，否则是两套口径。"""
        mla, high_result = _mla_with_both_levels()
        qs = mla.query_low_level_qs("high", "low", high_result.bis[-1])
        assert len(qs["bis"]) == qs["bi_count"]
        assert len(qs["zss"]) == qs["zs_count"]
        # 用同一份日线查询，窗口内应能命中真实结构
        assert qs["bi_count"] > 0

    def test_usable_by_cross_period_qujiantao(self) -> None:
        """端到端：这些对象能直接喂给逐信号区间套确认（真实数据路径成立）。"""
        from easy_tdx.chanlun.qujiantao import compute_qujiantao_cross_period

        mla, high_result = _mla_with_both_levels()
        qs = mla.query_low_level_qs("high", "low", high_result.bis[-1])
        if not qs["bis"] and not qs["zss"]:
            return  # 该窗口无低级别结构（数据相关），跳过
        mmds = list(high_result.mmds)
        if not mmds:
            return
        res = compute_qujiantao_cross_period(
            mmds,
            bis_low=qs["bis"],
            zss_low=qs["zss"],
            # 真实行情 ⇒ 不声明 synthetic
            synthetic=False,
        )
        assert len(res) == len(mmds)
        for r in res:
            if isinstance(r, dict):
                assert r["synthetic"] is False, "真实低级别数据路径不得被标为合成"
