"""V735 Round 9：原文第17课精确口径——用次级别线段构中枢。

原文（第17课）：
  「缠中说禅走势中枢由至少三个连续次级别走势类型的重叠部分构成。」

原文（第91课）：
  「笔是不能构成中枢的，这就是笔和线段以及线段以上的各种级别
    走势类型的最大区别。」

当前默认用**同级别笔**构中枢（第91课说不行）。
zs_from_xd=True 改用**同级别线段**（第91课允许，但仍非「次级别」）。
process_klines_cross_timeframe 用**次级别（30min）线段**构中枢 = 原文精确口径。

实测（sh600000 日线 + 30min）：
  默认（同级别笔）：中枢=14 信号=36
  zs_from_xd=True（同级别线段）：中枢=2 信号=4
  交叉级别（30min线段）：中枢=3 信号=5
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from easy_tdx.chanlun.analyser import ChanlunAnalyser
from easy_tdx.chanlun.config import ChanlunConfig

DATA_DIR = Path(__file__).resolve().parents[2] / "audit_data"
MIN_DIR = Path(__file__).resolve().parents[2] / "audit_data_min"


def _load(name: str, d: Path) -> pd.DataFrame:
    p = d / name
    if not p.exists():
        pytest.skip(f"缺少 {p}")
    rows = json.loads(p.read_text(encoding="utf-8"))
    df = pd.DataFrame(rows)
    df["datetime"] = pd.to_datetime(df["datetime"])
    return df


def test_cross_tf_produces_fewer_signals() -> None:
    """交叉级别中枢比默认少，信号也少。

    钉死：sh600000 日线，中枢 28→3、信号 53→6。
    如果交叉级别方法坏了（退回默认），中枢=28≠3，测试会红。

    V851 口径修正：原断言「信号=5」是**索引错位下的产物**。
    `find_zss(lower_xds)` 产出的 `ZS.lines[*].index` 是 30min 线段序号，
    而 `mmd.py` 把它当日线笔下标用，导致 `bis[last_idx+1]` 取到
    时间上相差 4000+ 天的笔。修复（`_remap_cross_zs_indices`）后
    回试段归位，信号 5 → 6。
    实测（scripts/audit_cross_timeframe_remap_compare.py，14 只标的）：
    日期差从 3901–4382 天降到 3–46 天，ZG/ZD 区间 14/14 完全不变
    （证明只改 index 口径，不改中枢本身）。
    """
    df_d = _load("sh600000_daily.json", DATA_DIR)
    df_30 = _load("sh600000_30min.json", MIN_DIR)
    cfg = ChanlunConfig()

    a = ChanlunAnalyser(config=cfg)
    r = a.process_klines_cross_timeframe(df_d, df_30)
    assert len(r.zss) == 3, f"交叉级别中枢应为 3，实际 {len(r.zss)}"
    assert len(r.mmds) == 6, f"交叉级别信号应为 6（V851 索引修正后），实际 {len(r.mmds)}"


def test_cross_tf_zs_from_lower_xd_not_daily_bi() -> None:
    """交叉级别中枢的 lines 是 30min 线段（XD），不是日线笔（BI）。

    如果中枢来自日线笔，lines[0] 应是 BI 类型；
    来自 30min 线段，lines[0] 应是 XD 类型。
    """
    df_d = _load("sh600000_daily.json", DATA_DIR)
    df_30 = _load("sh600000_30min.json", MIN_DIR)
    cfg = ChanlunConfig()
    a = ChanlunAnalyser(config=cfg)
    r = a.process_klines_cross_timeframe(df_d, df_30)
    for zs in r.zss:
        for line in zs.lines:
            assert type(line).__name__ == "XD", (
                f"交叉级别中枢 lines 应为 XD（30min线段），"
                f"实际 {type(line).__name__}"
            )


def test_cross_tf_zero_overlap() -> None:
    """交叉级别中枢也有 0 重叠（zs_merge_overlap 生效）。"""
    df_d = _load("sh600000_daily.json", DATA_DIR)
    df_30 = _load("sh600000_30min.json", MIN_DIR)
    cfg = ChanlunConfig()
    a = ChanlunAnalyser(config=cfg)
    r = a.process_klines_cross_timeframe(df_d, df_30)
    ov = sum(
        1
        for i in range(1, len(r.zss))
        if r.zss[i - 1].zd < r.zss[i].zg and r.zss[i].zd < r.zss[i - 1].zg
    )
    assert ov == 0, f"交叉级别中枢重叠 {ov} 对（应为 0）"


def test_cross_tf_saves_lower_xds() -> None:
    """次级别线段保存在 xds_l1 供前端展示。"""
    df_d = _load("sh600000_daily.json", DATA_DIR)
    df_30 = _load("sh600000_30min.json", MIN_DIR)
    cfg = ChanlunConfig()
    a = ChanlunAnalyser(config=cfg)
    r = a.process_klines_cross_timeframe(df_d, df_30)
    assert len(r.xds_l1) > 0, "次级别线段应保存在 xds_l1"
    assert len(r.xds_l1) >= 20, f"30min 线段应有 ≥20，实际 {len(r.xds_l1)}"


def test_cross_tf_different_from_default() -> None:
    """交叉级别中枢 ≠ 默认中枢（证明用的是不同级别数据）。

    V735 Round 10 原断言「默认 zss==2（zs_from_xd=True 日线线段）」。
    该绝对值已**失效**：`ChanlunConfig()` 默认 `zs_from_xd=False`
    （见 config.py 的 V842 重核注释），默认路径用**同级别笔**构中枢，
    实测 sh600000 默认 zss=28，不是 2。

    V851：本测试改断言「中枢数与信号数都不同」这一**行为属性**，
    不再钉失效的绝对值。绝对值的正确性由
    `test_cross_tf_produces_fewer_signals` 单独锁定（zss==3, mmds==6）。
    """
    df_d = _load("sh600000_daily.json", DATA_DIR)
    df_30 = _load("sh600000_30min.json", MIN_DIR)
    cfg = ChanlunConfig()

    # 默认（同级别笔构中枢，zs_from_xd 默认 False）
    a1 = ChanlunAnalyser(config=cfg)
    r1 = a1.process_klines(df_d)
    # 交叉级别（30min线段构中枢）
    a2 = ChanlunAnalyser(config=cfg)
    r2 = a2.process_klines_cross_timeframe(df_d, df_30)

    # 中枢数必须不同（默认 28 vs 交叉 3）—— 证明用的是不同级别数据
    assert len(r1.zss) != len(r2.zss), (
        f"中枢数应不同：默认 {len(r1.zss)} vs 交叉 {len(r2.zss)}"
    )
    # 交叉级别中枢远少于默认（30min 线段粒度更粗）
    assert len(r2.zss) < len(r1.zss), (
        f"交叉级别中枢应更少：默认 {len(r1.zss)} vs 交叉 {len(r2.zss)}"
    )
    # 信号数也应不同
    assert len(r2.mmds) != len(r1.mmds), (
        f"信号数应不同：交叉 {len(r2.mmds)} vs 默认 {len(r1.mmds)}"
    )
    # 交叉级别中枢的 lines 必须是 XD（30min 线段），不是日线 BI
    for zs in r2.zss:
        for line in zs.lines:
            assert type(line).__name__ == "XD", (
                f"交叉级别中枢 lines 应为 XD（30min线段），实际 {type(line).__name__}"
            )


def test_zs_cross_timeframe_default_false() -> None:
    """默认 False（保持实用性）。"""
    assert ChanlunConfig().zs_cross_timeframe is False
