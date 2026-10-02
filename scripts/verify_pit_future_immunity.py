#!/usr/bin/env python3
"""PIT「未来免疫」探针：往输入里追加未来数据，结论必须纹丝不动。

为什么要它
----------
上一轮用「正则扫 target 参数 + 尾部切片」找出了一个真实泄漏（`detect_season`
过滤了收盘价却没过滤量能）。但正则扫描只能匹配代码形状，换个写法就漏。
本探针改成**运行时行为判定**，不依赖代码长什么样：

    result(数据截至 T)  ==  result(数据截至 T + 追加任意未来数据)

若不等，就是用了 target 之后的未来数据。这才是 PIT 纪律的可执行定义。

覆盖对象（P1 生命线相关的时点函数）
----------------------------------
1. `detect_season`（F7 四季）：追加未来的价、量，季节不得变。
2. `pick_report`（F8 选期）：追加一条未来披露的财报，选期不得变。

用法：  .venv/bin/python scripts/verify_pit_future_immunity.py
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd  # noqa: E402

from easy_tdx.fundamental.indicators import load_all_periods_frame, pick_report  # noqa: E402
from easy_tdx.fundamental.season import detect_season  # noqa: E402

N = 320
T_IDX = 150
BASE = date(2024, 1, 1)
CACHE = Path.home() / ".easy_tdx" / "gpcw_cache"

_fails: list[str] = []


def _check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'✅' if ok else '❌'} {name}" + (f"  {detail}" if detail else ""))
    if not ok:
        _fails.append(name)


# ── 1. 四季：追加未来的价与量 ────────────────────────────
def test_season_future_immunity() -> None:
    print("F7 四季 —— 追加未来 K 线（价/量同时变化）")
    dates = [BASE + timedelta(days=i) for i in range(N)]
    closes = [100.0 + 3.0 * (i // 30) for i in range(N)]
    vols = [1000.0 + (i % 13) * 40 for i in range(N)]
    target = dates[T_IDX]

    base = detect_season(dates, closes, target, volumes=vols)

    # 追加 60 根未来 K 线：价格暴涨 + 最后 5 根量能暴涨
    fut_d = [dates[-1] + timedelta(days=k) for k in range(1, 61)]
    fut_c = [closes[-1] * (1.0 + 0.01 * k) for k in range(1, 61)]
    fut_v = [1000.0] * 55 + [999_999.0] * 5

    ext_d, ext_c, ext_v = dates + fut_d, closes + fut_c, vols + fut_v
    ext = detect_season(ext_d, ext_c, target, volumes=ext_v)

    _check(
        "季节结论不变",
        base.season == ext.season,
        f"{base.season} -> {ext.season}",
    )
    _check(
        "量能信号不变",
        base.signals["vol_score2"] == ext.signals["vol_score2"],
        f"{base.signals['vol_score2']} -> {ext.signals['vol_score2']}",
    )
    _check(
        "总分不变",
        base.signals["total_score"] == ext.signals["total_score"],
        f"{base.signals['total_score']} -> {ext.signals['total_score']}",
    )


# ── 2. 选期：追加一条未来披露的财报 ──────────────────────
def test_pick_report_future_immunity() -> None:
    print("\nF8 选期 —— 追加一条未来披露的财报")
    zips = sorted(z.name for z in CACHE.glob("gpcw*.zip"))
    if not zips:
        print("  ⚠ 无 gpcw 缓存，跳过（未验证）")
        return
    frame = load_all_periods_frame(zips, None)
    if frame.empty:
        print("  ⚠ 指标帧为空，跳过（未验证）")
        return

    target = date(2026, 4, 30)
    pairs = frame[["code", "market"]].drop_duplicates().sort_values("code").head(120)
    changed = 0
    checked = 0
    for code, mkt in pairs.values:
        before = pick_report(frame, code, target, market=mkt)
        if before is None:
            continue
        # 追一条"更晚报告期 + 更晚披露日"的记录（纯未来数据）
        poison = pd.DataFrame([{
            "code": code, "market": mkt,
            "report_date": date(2027, 12, 31),
            "disclosure_date": date(2028, 4, 30),
            "roe": 99.0, "revenue": 9.9e12,
        }])
        poisoned = pd.concat([frame, poison], ignore_index=True)
        after = pick_report(poisoned, code, target, market=mkt)
        checked += 1
        if after is None or str(after.get("report_date")) != str(before.get("report_date")):
            changed += 1
            if changed <= 3:
                print(f"    ❌ {code}: {before.get('report_date')} -> "
                      f"{None if after is None else after.get('report_date')}")
    if checked < 20:
        _check("样本充足", False, f"仅 {checked} 只（<20），判定无效")
        return
    _check("未来财报不改变 T 时点的选期", changed == 0, f"检查 {checked} 只，异常 {changed}")


def main() -> int:
    print("PIT 未来免疫探针\n")
    test_season_future_immunity()
    test_pick_report_future_immunity()
    if _fails:
        print(f"\n结论: ❌ {len(_fails)} 项未通过未来免疫 —— {_fails}")
        return 1
    print("\n结论: ✅ 结论不因追加未来数据而改变（PIT 成立）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
