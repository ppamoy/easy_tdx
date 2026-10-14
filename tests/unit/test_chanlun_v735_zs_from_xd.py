"""V735：第91课「笔是不能构成中枢的」—— 构中枢组件的开关测试。

原文（第91课《走势结构的两重表里关系1》）：
  「……有两种类型：一、能构成中枢的。二、不能构成中枢的。
    第一种，包括**线段、以及各种级别的走势类型**；第二种，只有笔。
    **笔是不能构成中枢的**，这就是笔和线段以及线段以上的各种级别
    走势类型的最大区别。」

代码主路径 `analyser.find_zss(bis)` 用**笔**构中枢 → 与第91课相反；
递归路径 `recursive` 用线段（当 BI 传入）构中枢 → 符合第91课。

新增开关 `config.zs_from_xd`：
  - False（**默认**）：笔构中枢（既有行为，信号密度高）
  - True：线段构中枢（第91课口径；但中枢落在更高近似级别，
    实测信号数下降 70%~90%）

⚠️ 默认保持 False：因为仅凭日线数据**无法**构造严格意义的日线中枢——
原文第17课要求中枢由**次级别走势类型**构成，日线的次级别是30分钟，
需次级别K线数据。用线段构中枢虽然"组件合规"，但落在更高级别
（见 docs/CHANLUN_FIDELITY_AUDIT_V735.md §19）。
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from easy_tdx.chanlun.analyser import ChanlunAnalyser
from easy_tdx.chanlun.config import ChanlunConfig

DATA_DIR = Path(__file__).resolve().parents[2] / "audit_data"


def _result(name: str, zs_from_xd: bool) -> object:
    p = DATA_DIR / name
    if not p.exists():
        pytest.skip(f"缺少 audit_data/{name}")
    rows = json.loads(p.read_text(encoding="utf-8"))
    df = pd.DataFrame(rows)
    df["datetime"] = pd.to_datetime(df["datetime"])
    cfg = ChanlunConfig()
    cfg.zs_from_xd = zs_from_xd
    return ChanlunAnalyser(config=cfg).process_klines(df)


def test_zs_from_xd_default_false() -> None:
    """默认 False = 笔构中枢（当前系统口径）。"""
    assert ChanlunConfig().zs_from_xd is False


def test_zs_from_xd_reduces_zs_and_signals() -> None:
    """线段构中枢（第91课口径）中枢与信号显著减少。

    钉死绝对值（sh000001 日线，V851 后重测）：
      笔构：34 中枢 / 68 信号
      线段构：0 中枢 / 0 信号（仅 1 线段，不足以构中枢）

    V851 说明：原钉死值「笔构 23 中枢 / 80 信号」是 V851 配置变更前的实测。
    V851 把 `zs_no_hard_close` / `zs_merge_overlap` 默认都改为 False 后
    （第33课 3+6=9 段上限 + 关闭同级别合并），同一份数据重测得 34/68。
    开关两侧实测（docs/CHANLUN_FIDELITY_AUDIT_V735.md §37.2）：
      旧默认(True+True) ：332 中枢样本上 >9 段 81 个（24.4%），最长 37 段
      新默认(False+False)：403 中枢样本上 >9 段 0 个（0.0%），最长 9 段
    线段构两侧都是 0/0，不受该配置变更影响。
    只断言"更少"没有牙齿（削弱一点仍满足），必须钉死绝对值。
    """
    bi = _result("sh000001_daily.json", False)
    xd = _result("sh000001_daily.json", True)
    n_zs_bi, n_mmds_bi = len(bi.zss), len(bi.mmds)
    n_zs_xd, n_mmds_xd = len(xd.zss), len(xd.mmds)

    assert n_zs_bi == 34, f"笔构中枢 中枢数应为 34，实际 {n_zs_bi}"
    assert n_mmds_bi == 68, f"笔构中枢 信号数应为 68，实际 {n_mmds_bi}"
    assert n_zs_xd == 0, f"线段构中枢 中枢数应为 0，实际 {n_zs_xd}"
    assert n_mmds_xd == 0, f"线段构中枢 信号数应为 0，实际 {n_mmds_xd}"
    # 线段更粗 ⇒ 中枢更少（0 < 34）
    assert n_zs_xd < n_zs_bi
    assert n_mmds_xd < n_mmds_bi


def test_zs_from_xd_true_uses_xd_segments() -> None:
    """True 时中枢的线来自线段：中枢总数应远少于笔数。

    齿：若开关失效（仍用笔），中枢数会回到 8，断言失败。
    """
    xd = _result("sh000001_daily.json", True)
    bi = _result("sh000001_daily.json", False)
    # 线段构成的 中枢，其线段数应远少于笔构成的
    assert len(xd.zss) < len(bi.zss), (
        f"线段构中枢 {len(xd.zss)} 应少于笔构中枢 {len(bi.zss)}"
    )
