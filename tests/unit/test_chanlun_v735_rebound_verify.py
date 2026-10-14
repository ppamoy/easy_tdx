"""V735：第29课「背驰-转折定理」后置验证 + 信号可信度扣分测试。

原文（第29课，定理级）：
  「缠中说禅背驰-转折定理：某级别趋势的背驰将导致该趋势最后一个中枢
    的级别扩展、该级别更大级别的盘整或该级别以上级别的反趋势。」
  「该反弹**一定触及**最后一个中枢的 DD=min(dn)，也就是围绕该中枢
    震荡的最低点，否则……就等于在下面又至少形成一个新的……中枢，
    这与上中枢是最后一个矛盾。」

实测（10 只日线 / 68 个 1买）：91% 触及 DD（符合定理），9% 未触及。

⚠️ 这是**后置验证**（信号产生后才能检查反弹是否触及），不是前置过滤器。
   只设 `_rebound_verified` 质量标记，不改信号有无。
   Round 8 起：未通过验证的 1买/1卖 decision_score 扣减 rebound_penalty（默认 15 分）。
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from easy_tdx.chanlun.analyser import ChanlunAnalyser
from easy_tdx.chanlun.config import ChanlunConfig

DATA_DIR = Path(__file__).resolve().parents[2] / "audit_data"


def _result(name: str) -> object:
    rows = json.loads((DATA_DIR / name).read_text(encoding="utf-8"))
    df = pd.DataFrame(rows)
    df["datetime"] = pd.to_datetime(df["datetime"])
    return ChanlunAnalyser(config=ChanlunConfig(zs_from_xd=False)).process_klines(df)


def test_1buy_gets_rebound_verified_flag() -> None:
    """每个 1买/1卖 都应有 `_rebound_verified` 标记（True/False/None）。"""
    p = DATA_DIR / "sh600009_daily.json"
    if not p.exists():
        pytest.skip("缺少 audit_data/sh600009_daily.json")
    r = _result("sh600009_daily.json")
    flagged = 0
    for m in r.mmds:
        if m.mmd_type.value in ("1buy", "1sell"):
            assert hasattr(m, "_rebound_verified"), f"{m.mmd_type.value} 缺标记"
            flagged += 1
    assert flagged > 0, "应有至少 1 个 1买/1卖"


def test_rebound_verified_is_not_all_true() -> None:
    """不是所有 1买 都通过验证 —— 部分未触及 DD/GG（定理的偏离）。

    如果全 True，说明验证逻辑可能没真跑（形同虚设）。
    V851 重测：sh600009 实测 27 个 1买/1卖，其中 1 个未通过。
    （旧值 14/2 是 V735 配置下的产物。V851 改默认
     zs_no_hard_close=False + zs_merge_overlap=False 后，中枢数
     23→34，1买/1卖 14→27，未通过 2→1 —— 测试牙齿仍在：
     仍有 1 个未通过验证的 1买，逻辑非形同虚设。）
    """
    p = DATA_DIR / "sh600009_daily.json"
    if not p.exists():
        pytest.skip("缺少 audit_data/sh600009_daily.json")
    r = _result("sh600009_daily.json")
    total = sum(1 for m in r.mmds if m.mmd_type.value in ("1buy", "1sell"))
    verified = sum(
        1
        for m in r.mmds
        if m.mmd_type.value in ("1buy", "1sell")
        and getattr(m, "_rebound_verified", None) is True
    )
    failed = sum(
        1
        for m in r.mmds
        if m.mmd_type.value in ("1buy", "1sell")
        and getattr(m, "_rebound_verified", None) is False
    )
    assert total == 27, f"1买/1卖 总数应为 27，实际 {total}"
    assert verified == 26, f"通过验证应为 26，实际 {verified}"
    assert failed == 1, f"未通过验证应为 1，实际 {failed}"


def test_rebound_verified_does_not_filter_signals() -> None:
    """后置验证只设标记，不改信号数量（不能变成过滤器）。"""
    p = DATA_DIR / "sh600009_daily.json"
    if not p.exists():
        pytest.skip("缺少 audit_data/sh600009_daily.json")
    r = _result("sh600009_daily.json")
    # 1买/1卖 数量不因验证而减少（V851 实测 27）
    assert sum(1 for m in r.mmds if m.mmd_type.value in ("1buy", "1sell")) == 27


def test_rebound_penalty_applied_to_failed() -> None:
    """未通过验证的 1买/1卖 decision_score 扣减 15 分。

    钉死：sh600009 的 1 个未通过验证的 1买/1卖，factors.rebound_penalty == -15。
    （V851 实测：27 个 1买/1卖中 1 个未通过；旧值为 2 个。）
    """
    p = DATA_DIR / "sh600009_daily.json"
    if not p.exists():
        pytest.skip("缺少 audit_data/sh600009_daily.json")
    r = _result("sh600009_daily.json")
    penalized = 0
    for m in r.mmds:
        if m.mmd_type.value not in ("1buy", "1sell"):
            continue
        if getattr(m, "_rebound_verified", None) is not False:
            continue
        dq = getattr(m, "_decision_quality_score", None)
        assert dq is not None, f"{m.mmd_type.value} 缺决策质量分"
        factors = dq.get("factors", {})
        assert factors.get("rebound_penalty") == -15.0, (
            f"未通过验证应扣 15 分，实际 factors={factors}"
        )
        penalized += 1
    assert penalized == 1, f"应有 1 个被扣分，实际 {penalized}"


def test_rebound_penalty_not_applied_to_verified() -> None:
    """通过验证的 1买/1卖 不受扣分影响。

    钉死：sh600009 的 26 个通过验证的 1买/1卖，factors 无 rebound_penalty。
    （V851 实测：27 个 1买/1卖中 26 个通过；旧值为 12 个。）
    """
    p = DATA_DIR / "sh600009_daily.json"
    if not p.exists():
        pytest.skip("缺少 audit_data/sh600009_daily.json")
    r = _result("sh600009_daily.json")
    clean = 0
    for m in r.mmds:
        if m.mmd_type.value not in ("1buy", "1sell"):
            continue
        if getattr(m, "_rebound_verified", None) is not True:
            continue
        dq = getattr(m, "_decision_quality_score", None)
        assert dq is not None
        factors = dq.get("factors", {})
        assert "rebound_penalty" not in factors, (
            f"通过验证不应扣分，实际 factors={factors}"
        )
        clean += 1
    assert clean == 26, f"应有 26 个不受扣分，实际 {clean}"


def test_rebound_penalty_zero_disables() -> None:
    """rebound_penalty=0 时不扣分（证明扣分是开关控制的）。"""
    p = DATA_DIR / "sh600009_daily.json"
    if not p.exists():
        pytest.skip("缺少 audit_data/sh600009_daily.json")
    rows = json.loads(p.read_text(encoding="utf-8"))
    df = pd.DataFrame(rows)
    df["datetime"] = pd.to_datetime(df["datetime"])
    cfg = ChanlunConfig(zs_from_xd=False)
    cfg.rebound_penalty = 0.0
    r = ChanlunAnalyser(config=cfg).process_klines(df)
    for m in r.mmds:
        if m.mmd_type.value not in ("1buy", "1sell"):
            continue
        if getattr(m, "_rebound_verified", None) is not False:
            continue
        dq = getattr(m, "_decision_quality_score", None)
        assert dq is not None
        factors = dq.get("factors", {})
        assert "rebound_penalty" not in factors, (
            "rebound_penalty=0 时不应扣分"
        )


def test_rebound_penalty_default_15() -> None:
    """默认扣分 15.0 分。"""
    assert ChanlunConfig(zs_from_xd=False).rebound_penalty == 15.0
