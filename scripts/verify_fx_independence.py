#!/usr/bin/env python3
"""分型独立性巡检 —— 缠论原文硬约束。

缠论原文要求：**相邻分型不得共用K线**（顶底之间至少要有 1 根「既不属于顶分型
也不属于底分型」的独立K线），且分型序列必须顶底严格交替。

`fractal.find_fractals` 是逐三根滑动窗口扫描，天然会产出共用K线的相邻分型
（如「底-顶-底」挤在连续三根K线上），这类分型**不是独立的分型**，不能直接
渲染给人看。因此展示层必须用 `valid_fractals`（笔端点分型 + 独立性兜底）。

本脚本审计两类字段，**判定标准不同**：
  · valid_fractals —— 展示层字段，必须零违规。有违规即真 bug。
  · fractals       —— 原始滑动窗口产物，长期有告警是预期的，仅供参考。

三种笔口径（new/old/simple）全覆盖：simple 是 legacy 口径，其 gap 规则形同
虚设，最容易让 valid_fractals 退化，只测默认 new 会漏掉这类 bug。
注意 bi_type 不经 HTTP 接口暴露（/chanlun/analyze 不接受该参数），故本脚本
直接调用 ChanlunAnalyser，不走 HTTP。

用法：
    .venv/bin/python scripts/verify_fx_independence.py            # 默认样本
    .venv/bin/python scripts/verify_fx_independence.py SZ 000001 DAY

退出码：0 = valid_fractals 无违规，1 = valid_fractals 有违规
"""
from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

import pandas as pd  # noqa: E402

from easy_tdx.chanlun import ChanlunAnalyser, ChanlunConfig  # noqa: E402

BASE = os.environ.get("EASY_TDX_API", "http://127.0.0.1:8000")
DEFAULT_CASES = [
    ("SZ", "000001", "DAY"),
    ("SH", "600519", "DAY"),
    ("SZ", "000333", "DAY"),
    ("SH", "601318", "DAY"),
    ("SZ", "000001", "MIN_30"),
    ("SZ", "000001", "WEEK"),
]


# 三种笔口径都测。simple 是 legacy 口径，其 gap 规则形同虚设，最容易让
# valid_fractals 退化——只测默认 new 会漏掉这类 bug（坏版本回归实证）。
BI_TYPES = ("new", "old", "simple")

MIN_GAP = {"new": 3, "old": 5, "simple": 3}


def fetch(case: tuple[str, str, str], bi_type: str = "new") -> dict:
    """取 K 线并现场跑缠论分析。

    不走 /chanlun/analyze HTTP 接口：该接口不接受 bi_type 参数（传了会被忽略），
    无法覆盖 simple 口径，故直接调 ChanlunAnalyser。
    """
    market, code, category = case
    q = urllib.parse.urlencode(
        {"market": market, "code": code, "category": category, "start": 0, "count": 800}
    )
    rows = json.loads(
        urllib.request.urlopen(f"{BASE}/api/v1/bars?{q}", timeout=180).read()
    )["data"]
    result = ChanlunAnalyser(
        code=market + code,
        frequency="daily",
        config=ChanlunConfig(bi_type=bi_type),
    ).process_klines(pd.DataFrame(rows))
    return {
        "fractals": result.fractals,
        "valid_fractals": result.valid_fractals,
        "_bi_type": bi_type,
    }


def _audit(fxs: list[Any], bi_type: str = "new") -> list[str]:
    """对分型列表做独立性审计，返回违规描述列表。

    接受 FX 对象（直接调 analyser 时的形态）。间距用缠论K线 index 计算，
    口径与 bi.py::_check_bi_gap 完全一致。
    """
    errs: list[str] = []
    min_gap = MIN_GAP.get(bi_type, 3)
    for i in range(len(fxs) - 1):
        a, b = fxs[i], fxs[i + 1]
        ta = a.fx_type.value if hasattr(a.fx_type, "value") else str(a.fx_type)
        tb = b.fx_type.value if hasattr(b.fx_type, "value") else str(b.fx_type)
        ka = a.klines or []
        kb = b.klines or []
        if not ka or not kb:
            continue
        gap = kb[0].index - ka[-1].index + 1
        if ta == tb:
            errs.append(f"[{i}] {ta}@{a.bar_index} 与 {tb}@{b.bar_index} 同类型相邻")
            continue
        if gap < min_gap:
            errs.append(
                f"[{i}] {ta}@{a.bar_index} -> {tb}@{b.bar_index}："
                f"独立K线不足（gap {gap} < {min_gap}）"
            )
    return errs


def check(
    case: tuple[str, str, str], bi_type: str = "new"
) -> tuple[list[str], list[str], int, int]:
    """返回 (原始分型违规, valid_fractals违规, 原始条数, valid条数)。"""
    d = fetch(case, bi_type)
    raw = d.get("fractals", [])
    vf = sorted(d.get("valid_fractals", []), key=lambda f: f.bar_index)
    return _audit(raw, bi_type), _audit(vf, bi_type), len(raw), len(vf)


def main() -> int:
    if len(sys.argv) == 4:
        cases = [(sys.argv[1], sys.argv[2], sys.argv[3])]
    else:
        cases = DEFAULT_CASES

    total_raw = 0
    total_raw_fx = 0
    total_vf = 0
    total_vf_n = 0

    for case in cases:
        for bi_type in BI_TYPES:
            errs_raw, errs_vf, n_raw, n_vf = check(case, bi_type)
            total_raw += len(errs_raw)
            total_raw_fx += n_raw
            total_vf += len(errs_vf)
            total_vf_n += n_vf
            name = f"{'/'.join(case)} [{bi_type}]"
            if errs_vf:
                print(f"❌ {name}: **valid_fractals 违规 {len(errs_vf)} 处**（共 {n_vf} 个）")
                for e in errs_vf[:3]:
                    print(f"      {e}")
                if len(errs_vf) > 3:
                    print(f"      ... 另有 {len(errs_vf) - 3} 处")
            else:
                print(f"✅ {name}: valid_fractals {n_vf} 个，全部合规")

    print()
    print(f"【展示层字段 valid_fractals】违规 {total_vf} 处 / {total_vf_n} 个  "
          f"-> {'✅ 通过' if total_vf == 0 else '❌ 必须修复'}")
    print(f"【原始字段 fractals】     违规 {total_raw} 处 / {total_raw_fx} 个  "
          f"（固有产物，仅供参考）")
    print()
    print(
        "说明：本脚本同时审计两个字段，但**判定标准不同**：\n"
        "  · valid_fractals 是给展示层用的，必须零违规 —— 有违规就是真 bug。\n"
        "  · fractals 是 find_fractals 逐三根滑动窗口的产物，天然含共用K线的\n"
        "    重叠分型，**长期有告警是预期的**，不算 bug。它仅供内部计算使用。\n"
        "\n"
        "  若 valid_fractals 出现违规，常见原因：某页面/接口回退到渲染原始\n"
        "  fractals，或 bi_type 配置让笔端点集合退化（已由\n"
        "  analyser._enforce_fx_independence 兜底，若兜底失效则在此暴露）。"
    )
    return 1 if total_vf else 0


if __name__ == "__main__":
    raise SystemExit(main())
