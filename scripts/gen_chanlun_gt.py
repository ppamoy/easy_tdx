#!/usr/bin/env python3
"""为前端逐点坐标契约测试生成 ground truth（V733）。

用**真后端** `easy_tdx.chanlun.analyser` 跑真 fixture，输出每个买卖点的
`bar_index` / `anchor_val`，连同 K 线一起写进
`web-ui/src/components/__tests__/__fixtures__/chanlun_gt.json`，
供 `chanlun-coord-mapping.test.ts` 逐点比对组件画出来的标记坐标。

为什么不能手写 fixture：手造 K 线里 bar_index 与数组下标一一对应，
真实数据里二者会错位（前后复权/停牌/分钟级多根），
正是要锁住的那类 bug。

运行：  .venv/bin/python scripts/gen_chanlun_gt.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

FIXTURES = ROOT / "tests" / "fixtures"
OUT = ROOT / "web-ui" / "src" / "components" / "__tests__" / "__fixtures__" / "chanlun_gt.json"


def _freq(stem: str) -> str:
    if "weekly" in stem:
        return "weekly"
    if "daily" in stem:
        return "daily"
    if "30min" in stem:
        return "30min"
    return "daily"


def main() -> int:
    import pandas as pd

    from easy_tdx.chanlun.analyser import ChanlunAnalyser
    from easy_tdx.chanlun.config import ChanlunConfig

    cases: dict[str, dict] = {}
    for path in sorted(FIXTURES.glob("chanlun_*.json")):
        rows = json.loads(path.read_text(encoding="utf-8"))
        stem = path.stem
        res = ChanlunAnalyser(
            code=stem, frequency=_freq(stem), config=ChanlunConfig()
        ).process_klines(pd.DataFrame(rows))

        mmds = []
        for m in res.mmds:
            bi = m.bi
            if bi is None or bi.end is None:
                continue
            mmds.append(
                {
                    "type": m.mmd_type.value,
                    "bar_index": bi.end.bar_index,
                    "anchor_val": getattr(bi.end, "val", None),
                    "date": str(rows[bi.end.bar_index]["datetime"])[:10]
                    if bi.end.bar_index is not None and bi.end.bar_index < len(rows)
                    else None,
                }
            )
        if not mmds:
            print(f"{stem}: 无买卖点，跳过")
            continue

        bars = [
            {
                "datetime": str(r["datetime"]),
                "open": float(r["open"]),
                "close": float(r["close"]),
                "high": float(r["high"]),
                "low": float(r["low"]),
                "vol": float(r.get("vol", 0) or 0),
                "amount": float(r.get("amount", 0) or 0),
            }
            for r in rows
        ]
        cases[stem] = {"bars": bars, "mmds": mmds}
        print(f"{stem}: {len(bars)} 根 K 线 / {len(mmds)} 个买卖点")

    if not cases:
        print("❌ 没有任何用例产出买卖点 ⇒ fixture 会空转通过")
        return 1

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(cases, ensure_ascii=False, indent=1), encoding="utf-8")
    total = sum(len(c["mmds"]) for c in cases.values())
    print(f"\n✅ 写入 {OUT.relative_to(ROOT)}：{len(cases)} 个用例 / {total} 个买卖点")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
