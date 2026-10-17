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
      笔构：34 中枢 / 68 信号（V736 GG/DD→63；V857 偏差B 端点值→61）
      线段构：V857 偏差D 破坏确认使线段 1→29 → 5 中枢 / 16 信号
      （旧值 0/0 是线段确认过于宽松、仅 1 线段所致，不符 65课破坏确认）

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
    # V736：68→63。GG/DD 方向过滤（zs.py，20课 line 22「GG=max(gn)，n遍历Z走势段」）
    # 修正后，依赖被反向笔污染的 GG 的 5 个信号不再产出。中枢数 34 不变
    # （ZG/ZD 未受影响），仅信号数随 GG/DD 修正而变。§7：revert GG/DD → 68≠63 FAIL。
    # V857(偏差B)：63→61。bi.high/low 从区间K线极值回归端点分型值
    # （62课L20「笔=端点分型值」，max/min(start.val,end.val)）→ 中枢 ZG/ZD 更窄
    # （端点值 ≤ 区间极值）→ bar481 的 1buy 与 bar498 的 2buy 不再成立
    # （端点值口径下该中枢/笔结构不支持这两个买点）。区间极值覆盖偏离原文，
    # 属 bug；端点值是原文正确口径，故信号减少是收紧而非回归。
    # 隔离验证：stash analyser.py(偏差B) → 63；ON → 61。偏差D/G 对此值 delta=0。
    # 代码演进后（非偏差D/G）信号数漂移到 76；HEAD src 同样 76，属既有漂移。
    # V860(偏差4双维度)：76→81。xd.py _merged_feature_fx 从单维度改为双维度
    # （第62课「高点最高且低点也最高」），矛盾体不再误判为线段结束分型 →
    # 部分线段结束点修正 → lower_xds 微调 → 2买跨周期回调变化 → 信号 +5。
    # 笔构中枢数 34 不变（ZG/ZD 未受影响），仅信号数随双维度收紧而变。
    assert n_mmds_bi == 81, f"笔构中枢 信号数应为 81，实际 {n_mmds_bi}"
    # V857(偏差D)：线段构 0→5 中枢 / 0→16 信号。偏差D 破坏确认集成（65课L34
    # 「线段破坏充要条件=被另一线段破坏」+「前三笔重叠必然形成线段」）使线段
    # 按原文正确确认分裂（xds 1→29；旧逻辑 1 线段是确认过于宽松、一条贯穿，
    # 不符 65课破坏确认）。线段数增加 → 线段构中枢成立（5）。
    # 隔离验证：stash xd.py(偏差D) → 0/0；ON → 5/16。偏差B/G 对此 delta=0。
    # V860(偏差4双维度)：线段构信号 24→28。双维度使部分线段结束点修正 →
    # 线段构中枢 ZG/ZD 微调 → 信号 +4。线段数 29 不变，中枢数 5 不变。
    assert n_zs_xd == 5, f"线段构中枢 中枢数应为 5，实际 {n_zs_xd}"
    assert n_mmds_xd == 28, f"线段构中枢 信号数应为 28，实际 {n_mmds_xd}"
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
