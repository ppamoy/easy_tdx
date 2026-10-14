"""V735 起测「相邻中枢重叠率」；V851 重核引文并推翻默认值。

⚠️ V851 引文更正（原判定错误，已修正）：
  原模块 docstring 把「相邻中枢不能有任何重叠」归给**第19课**，并据此把
  `zs_merge_overlap` 默认设为 True。该引文在 108 课原文里 **grep 不到**。

  已全文检索「不能有任何重叠」，唯一命中是 **第20课 line 4**：
  「而在趋势里，同级别的前后缠中说禅走势中枢是不能有任何重叠的，这包括
    任何围绕走势中枢产生的任何瞬间波动之间的重叠。因此，如果三个连续
    次级别走势类型的重叠区间虽然不和前面的走势中枢有任何重叠，但围绕
    该中枢产生的波动触及前面走势中枢延续时的某个瞬间波动区间，这时候，
    就不能认为该走势类型是趋势，而只是产生一个**更大级别的**缠中说禅
    走势中枢。」
  ⇒ 原文口径：前后中枢重叠 ⇒ **升级为更大级别中枢**，不是把同级别
    中枢段数相加。

  而 `_merge_overlapping_zss` 做的是 `prev.lines.extend(zs.lines)`
  （同级别段数相加），既不是升级，也违反第33课的 3+6=9 段上限。

V851 实测（scripts/audit_g1_merge_overlap_impact.py，12 只真实日线 332 中枢）：
  A 无限延伸+合并开（V735 默认）: >9段 81 (24.4%)，最长 37 段
  B 硬关闭  +合并开             : >9段 58 (17.8%)，最长 32 段（合并触发 3→77 对）
  C 硬关闭  +合并关（V851 默认）: >9段  0 ( 0.0%)，最长  9 段 = 第33课上限
  信号数：658 → 650（-1.2%）

V851 决策：两个默认都改为 False。本文件保留 merge 的**机械行为**测试
（merge=True 确实能消除重叠 + merge=False 确实有重叠），原文符合性由
默认值测试保证。
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from easy_tdx.chanlun.analyser import ChanlunAnalyser
from easy_tdx.chanlun.config import ChanlunConfig

DATA_DIR = Path(__file__).resolve().parents[2] / "audit_data"


def _overlap_pairs(n_files: int = 6, merge: bool = True, hard: bool = False) -> tuple[int, int]:
    """返回 (相邻中枢对总数, [zd,zg] 重叠数)。

    V851：`hard` 参数控制 `zs_no_hard_close`。对照组必须与
    `test_zs_merge_overlap_default_false` 的新默认（hard=False）一致，
    否则对照组测的是已废弃的旧配置。
    """
    cfg = ChanlunConfig(zs_from_xd=False)
    cfg.zs_merge_overlap = merge
    cfg.zs_no_hard_close = hard
    tot = 0
    ov = 0
    for p in sorted(DATA_DIR.glob("*_daily.json"))[:n_files]:
        rows = json.loads(p.read_text(encoding="utf-8"))
        if len(rows) < 200:
            continue
        df = pd.DataFrame(rows)
        df["datetime"] = pd.to_datetime(df["datetime"])
        r = ChanlunAnalyser(config=cfg).process_klines(df)
        zss = getattr(r, "zss", []) or []
        for i in range(1, len(zss)):
            a, b = zss[i - 1], zss[i]
            tot += 1
            if a.zd < b.zg and b.zd < a.zg:
                ov += 1
    return tot, ov


def test_overlap_zero_after_merge() -> None:
    """zs_merge_overlap=True 后重叠率降为 0%。

    钉死：6 只日线 / 200 对相邻中枢，**0 对重叠**。

    ⚠️ V851 更正：原注释引「第19课原文：前后两个中枢不能有任何重叠」
    作为合并依据 —— 该引文在 108 课原文里 **grep 不到**。唯一命中是
    **第20课 line 4**：「在趋势里，同级别的前后缠中说禅走势中枢是不能
    有任何重叠的……这时候，就不能认为该走势类型是趋势，而只是产生一个
    更大级别的缠中说禅走势中枢。」
    ⇒ 原文口径是**升级**，而 `_merge_overlapping_zss` 做的是
       `prev.lines.extend(zs.lines)`（同级别段数相加）—— 非原文语义。

    本测试仍保留：它验证的是「merge=True 确实能消除重叠」这一
    **机械行为**（不是验证原文符合性）。原文符合性由
    `test_zs_merge_overlap_default_false` 的默认 False 保证。
    """
    tot, ov = _overlap_pairs(6, merge=True, hard=False)
    assert tot > 0, "应有至少 1 对相邻中枢"
    assert ov == 0, (
        f"相邻中枢重叠 {ov}/{tot} 对（{ov/tot:.1%}）。"
        "zs_merge_overlap=True 应将所有重叠中枢合并。"
    )


def test_merge_off_shows_overlap() -> None:
    """zs_merge_overlap=False 时仍有重叠（证明 merge 确实在工作）。

    V851 实测（6 只日线）：merge=False + hard=False（新默认）= 41/200 对重叠。
    对照组口径必须与默认一致（hard=False），否则测的是旧配置。

    这是 merge 的**对照组**——如果 merge 被破坏（永远不合并），
    此测试仍会过，但 test_overlap_zero_after_merge 会红。
    """
    tot, ov = _overlap_pairs(6, merge=False, hard=False)
    assert tot > 0
    assert ov >= 1, (
        f"merge=False 时应有 ≥1 对重叠，实际 {ov}/{tot}。"
        "如果 merge=False 也 0 重叠，说明数据变了或 find_zss 改了。"
    )


def test_zs_merge_overlap_default_false() -> None:
    """V851 起默认 False（关闭同级别合并，符合第20课/第33课）。

    V735 曾引「第19课：重叠中枢合并」把默认设为 True。该引文在 108 课
    原文里 grep 不到；已全文检索，唯一命中「不能有任何重叠」的是
    **第20课 line 4**，说的是「产生一个**更大级别的**缠中说禅走势中枢」
    = 升级，不是把同级别中枢段数相加。

    `_merge_overlapping_zss` 做的是 `prev.lines.extend(zs.lines)`，
    实测（12 只真实日线 332 中枢）：
      A 无限延伸+合并开: >9段 81 (24.4%)，最长 37 段
      B 硬关闭+合并开:   >9段 58 (17.8%)，最长 32 段（合并触发 3→77 对）
      C 硬关闭+合并关:   >9段 0  (0.0%)，最长  9 段 = 第33课上限
    ⇒ 合并是超限的直接元凶，默认必须 False。
    """
    assert ChanlunConfig(zs_from_xd=False).zs_merge_overlap is False


def test_no_hard_close_default_false() -> None:
    """V851 起默认 False（9 段硬关闭，符合第33课）。

    第33课 line 7：「中枢的延伸不能超过5段，一旦出现6段的延伸，
    加上形成中枢本身那三段，就构成更大级别的中枢了。」⇒ 3+6=9 段上限。

    实测（scripts/audit_g1_merge_overlap_impact.py，12 只日线 332 中枢）：
      True （V735 旧默认）: >9段 81 (24.4%)，最长 37 段
      False（V851 新默认）: >9段 0  (0.0%)，最长  9 段
    """
    assert ChanlunConfig(zs_from_xd=False).zs_no_hard_close is False
