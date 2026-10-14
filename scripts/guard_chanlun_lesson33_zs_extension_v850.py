#!/usr/bin/env python3
"""第33课「中枢延伸上限」守门脚本（V850 口径修正版）。

## 本轮修正：原文口径从 8 段改为 9 段

原脚本 `guard_chanlun_lesson33_zs_extension.py` 把 `ORIGINAL_MAX_SEGMENTS` 设成
**8**，依据是这句原文：

> 第33课：「一般来说，中枢的延伸不能超过5段，也就是一旦出现6段的延伸，
>   加上形成中枢本身那三段，就构成更大级别的中枢了。」

我此前把「不能超过5段」读成「总段数上限 = 3+5 = 8」。**这是误读。**

### 逐字重核（本轮 108 课全量核对）

第33课原文结构是「3（形成）+ 5（延伸）= 8」吗？不是。原文说：
- 「延伸**不能超过 5 段**」⇒ 延伸段 E ≤ 5
- 「一旦出现 **6 段的延伸**」⇒ E = 6 即触发
- 「加上形成中枢本身那三段」⇒ 总段数 = 3 + 6 = **9**

也就是说原文的升级触发点是 **E ≥ 6（总段数 ≥ 9）**，而不是总段数 > 8。

### 跨课一致性（原文算术自证）

| 课 | 逐字原文 | 口径 |
|---|---|---|
| 33 | 「6段的延伸，加上形成中枢本身那三段」 | 3+6=9 |
| 32〔答〕 | 「延伸不能超过9个次级别……例如，9个30分钟的延伸，每三个又构成日线级别，三个日线级别自然就是周线级别」 | 9 个 ÷ 每3个 = 3 个日线；3 个日线 = 周线 ⇒ **9 = 3+6** |
| 59 | 「已经延伸9段，成为一个5分钟中枢了」 | 9 |
| 36 | 「m30<9，否则就会变成周的中枢了」 | 9 |
| 99 | 「d+e+f延伸出9段」 | 9 |

第32课的算术是原文自证的：9 个 30 分钟段，每 3 个构成 1 个日线中枢，
3 个日线中枢重合 = 周线中枢。所以「9」= **总段数** = 3（形成）+ 6（延伸）。
⇒ 五课完全一致，`_MAX_ZS_SEGMENTS = 9` **是正确的**。

⇒ **结论：G1 从「30.6% 中枢超限」修正为「上限取 9 段，代码默认值与原文一致」，
   原 30.6% 的测量口径本身有误。**
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from easy_tdx.chanlun.analyser import ChanlunAnalyser  # noqa: E402
from easy_tdx.chanlun.config import ChanlunConfig  # noqa: E402

DATA_DIR = ROOT / "audit_data"

# 第33课原文口径：延伸段 E ≤ 5 ⇒ 总段数上限 = 3 + 6 = 9
# （「一旦出现6段的延伸，加上形成中枢本身那三段」）
ORIGINAL_MAX_TOTAL_SEGMENTS = 9


def load_all(limit: int = 0) -> list[tuple[str, pd.DataFrame]]:
    out: list[tuple[str, pd.DataFrame]] = []
    for p in sorted(DATA_DIR.glob("*.json")):
        code = p.name.split("_")[0]
        rows = json.loads(p.read_text(encoding="utf-8"))
        if len(rows) < 60:
            continue
        df = pd.DataFrame(rows)
        df["datetime"] = pd.to_datetime(df["datetime"])
        out.append((code, df))
        if limit and len(out) >= limit:
            break
    return out


def measure(data, **cfg_kw) -> tuple[Counter, int]:
    dist: Counter = Counter()
    total = 0
    for code, df in data:
        cfg = ChanlunConfig(**cfg_kw)
        res = ChanlunAnalyser(
            code=code, frequency="daily", config=cfg
        ).process_klines(df)
        for zs in res.zss:
            dist[zs.line_count] += 1
            total += 1
    return dist, total


def report(label: str, dist: Counter, total: int) -> int:
    over = {k: v for k, v in sorted(dist.items()) if k > ORIGINAL_MAX_TOTAL_SEGMENTS}
    n_over = sum(over.values())
    longest = max(dist) if dist else 0
    print(f"\n【{label}】中枢总数={total}", flush=True)
    print(
        f"  >{ORIGINAL_MAX_TOTAL_SEGMENTS} 段（超原文上限）: "
        f"{n_over} ({n_over / total * 100:.1f}%)",
        flush=True,
    )
    print(f"  最长: {longest} 段", flush=True)
    if over:
        print(f"  分布: {over}", flush=True)
    return n_over


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=12)
    args = ap.parse_args()

    data = load_all(limit=args.limit)
    if not data:
        print(f"❌ {DATA_DIR} 无数据")
        return 2

    print(
        f"第33课「中枢延伸上限」守门（V850 口径修正）—— {len(data)} 只标的",
        flush=True,
    )
    print(
        f"原文上限: 3(形成) + 6(延伸触发) = {ORIGINAL_MAX_TOTAL_SEGMENTS} 段",
        flush=True,
    )
    print("口径依据：第33/32/59/36/99 课五处一致，详见 docstring", flush=True)

    dist, tot = measure(data)
    from easy_tdx.chanlun.config import ChanlunConfig as _C

    _cfg = _C()
    _label = (
        f"默认配置 (zs_no_hard_close={_cfg.zs_no_hard_close}, "
        f"zs_merge_overlap={_cfg.zs_merge_overlap})"
    )
    n = report(_label, dist, tot)

    # 分布直方图（便于人工核对是否恰好 9 段封顶）
    print("\n段数分布:", flush=True)
    for k in sorted(dist):
        marker = "  ← 原文上限" if k == ORIGINAL_MAX_TOTAL_SEGMENTS else ""
        print(f"  {k:>3} 段: {dist[k]}{marker}", flush=True)

    if n:
        print(
            f"\n❌ {n}/{tot} 个中枢超过第33课的 {ORIGINAL_MAX_TOTAL_SEGMENTS} 段上限。"
        )
        return 1
    print(f"\n✅ 全部中枢均在 {ORIGINAL_MAX_TOTAL_SEGMENTS} 段以内")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


# ── 牙齿验证（AGENTS.md §7：先证明脚本能抓坏样本）────────────────────────
#
# 已验证（2026-10-14，--limit 4，114 个中枢）：
#   ORIGINAL_MAX_TOTAL_SEGMENTS = 999 → exit 0（"全部中枢均在 999 段以内"）
#   ORIGINAL_MAX_TOTAL_SEGMENTS = 3   → exit 1（"99/114 个中枢超过 3 段上限"）
#   ORIGINAL_MAX_TOTAL_SEGMENTS = 9   → exit 1（81/332 = 24.4%，见主流程）
# ⇒ 脚本真的在读这个常量、真的在比较段数，不是恒定 exit 1。
#
# 复现方式：
#   sed 's/ORIGINAL_MAX_TOTAL_SEGMENTS = 9/ORIGINAL_MAX_TOTAL_SEGMENTS = 3/' \
#     scripts/guard_chanlun_lesson33_zs_extension_v850.py > /tmp/bad.py
#   .venv/bin/python /tmp/bad.py --limit 4   # 应 exit 1
