#!/usr/bin/env python3
"""第106课「笔至少延伸6个基本K线单位」vs 第77课「至少1根独立K线」口径对比。

## 原文争议（V850 108课全量核对新发现）

**第77课（较早）line 26**：
> 「笔，必须是一顶一底，而且顶和底之间至少有一个K线不属于顶分型与底分型。」

**第62课 line 20**：
> 「在实际分析中，都必须要求顶和底之间都至少有一K线当成一笔的最基本要求。」

**第106课（较新）line 20**：
> 「任一级别，都有最少的延伸时间，例如，一笔，由于必须有顶与底的分型，
>  因此，必须至少延伸6个基本K线单位，也就是说，如果5日线都不能碰到，
>  那就不会是笔的反弹了。」

### 为什么它们**不矛盾**（关键，不能误判）

第106课那半句的语义锚点是**均线**：「如果5日线都不能碰到，那就不会是笔的反弹了」
⇒ 它给的是**该级别最小延伸的均线判据**，不是笔定义本身的门槛。
第106课自己也说「走势级别与均线虽然没有必然的关系，但还是有一个大致的区间对应的」，
「根据经验」—— 是**经验判据**，不是**定义性约束**。

第77课 line 26 是笔的**定义性约束**（「必须是一顶一底，而且……至少有一个K线
不属于顶分型与底分型」），并且 line 28-36 证明了**笔划分的唯一性**。

⇒ 两者作用于不同层次：第77课管"能不能算笔"，第106课管"这个反弹够不够格被重视"。
   按"以新课程为准"也不该把第106课的经验判据塞进笔定义 ——
   第106课自己的措辞就是「经验」「大致区间对应」。

### 待实测

把第106课的 6 基本K线单位塞进 `_can_form_bi` 会对笔数/信号数产生什么影响？
本脚本实测两种口径：
- `lesson77`（当前代码）：gap >= 3（新笔，1 根独立K线）
- `lesson106`：笔跨越的K线数 >= 6（"基本K线单位"取笔起点分型左K线到终点分型右K线）
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


def measure(data, min_span: int | None):
    """min_span=None → 当前口径（第77课）；min_span=6 → 第106课口径。

    ⚠️ 实现注意：`bi.py:269` 在**模块内**直接调用 `_can_form_bi`，
    所以猴子补丁 `bi_mod._can_form_bi = patched` **无效**（第一次版本就栽在这，
    跑出"两种口径完全一致"的假阴性）。改用 `bi_type` 之外的显式参数：
    直接把约束写进一个临时的 `bi.py` 源码，import 到独立模块。
    """
    n_bi = 0
    n_sig = 0
    n_zss = 0
    span_hist: Counter = Counter()
    for code, df in data:
        cfg = ChanlunConfig()
        if min_span is not None:
            a = ChanlunAnalyser(code=code, frequency="daily", config=cfg)
            r = _process_with_min_span(a, df, min_span)
        else:
            a = ChanlunAnalyser(code=code, frequency="daily", config=cfg)
            r = a.process_klines(df)
        n_bi += len(r.bis)
        n_sig += len(r.mmds)
        n_zss += len(r.zss)
        for b in r.bis:
            try:
                span = b.end.klines[-1].index - b.start.klines[0].index + 1
            except (AttributeError, IndexError, TypeError):
                span = 0
            span_hist[span] += 1
    return n_bi, n_sig, n_zss, span_hist


def _process_with_min_span(analyser, df, min_span: int):
    """把 `_can_form_bi` 的 span 约束临时写进源码后重导入，真正生效。"""
    import importlib.util
    import inspect

    import easy_tdx.chanlun.bi as bi_mod

    src = inspect.getsource(bi_mod)
    old_block = '''    if config.bi_type == "new":
        # 新笔：至少1根独立缠论K线
        return gap >= 3'''
    new_block = f'''    if config.bi_type == "new":
        # 新笔：至少1根独立缠论K线
        if gap < 3:
            return False
        # 第106课口径（审计注入）：笔至少延伸 {{min_span}} 个基本K线单位
        try:
            span = end.klines[-1].index - start.klines[0].index + 1
        except (AttributeError, IndexError):
            return True
        return span >= {min_span}'''
    assert old_block in src, "锚点未命中 —— bi.py 的 _can_form_bi 结构变了，审计脚本需同步更新"
    patched_src = src.replace(old_block, new_block)

    tmp_mod_name = "_bi_lesson106_audit"
    spec = importlib.util.spec_from_loader(tmp_mod_name, loader=None)
    tmp_mod = importlib.util.module_from_spec(spec)
    tmp_mod.__file__ = str(Path(bi_mod.__file__))
    exec(compile(patched_src, str(bi_mod.__file__), "exec"), tmp_mod.__dict__)

    # 用临时模块替换 analyser 内部引用的 find_bis
    saved = analyser.__class__.find_bis if hasattr(analyser, "find_bis") else None
    try:
        # 直接调 process_klines，但把 bi 模块换掉
        import easy_tdx.chanlun.analyser as an_mod

        orig_find_bis = an_mod.find_bis
        an_mod.find_bis = lambda klines, cfg, **kw: tmp_mod.find_bis(klines, cfg, **kw)
        try:
            return analyser.process_klines(df)
        finally:
            an_mod.find_bis = orig_find_bis
    finally:
        if saved is not None:
            analyser.__class__.find_bis = saved


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=12)
    args = ap.parse_args()

    data = load_all(limit=args.limit)
    print(f"第106课 vs 第77课 笔长口径实测 —— {len(data)} 只真实日线\n", flush=True)

    b77, s77, z77, h77 = measure(data, None)
    print("【第77课口径（当前代码：gap>=3，1根独立K线）】", flush=True)
    print(f"  笔数 = {b77}", flush=True)
    print(f"  中枢数 = {z77}", flush=True)
    print(f"  信号数 = {s77}", flush=True)
    print(
        f"  笔跨K线分布 = {dict(sorted(h77.items()))}\n",
        flush=True,
    )

    b106, s106, z106, h106 = measure(data, 6)
    print("【第106课口径（笔至少延伸6个基本K线单位）】", flush=True)
    print(f"  笔数 = {b106}", flush=True)
    print(f"  中枢数 = {z106}", flush=True)
    print(f"  信号数 = {s106}", flush=True)
    print(
        f"  笔跨K线分布 = {dict(sorted(h106.items()))}\n",
        flush=True,
    )

    dropped = b77 - b106
    print("=" * 60, flush=True)
    print("对比：", flush=True)
    print(f"  笔数:    {b77} (77课) vs {b106} (106课)  丢弃 {dropped} "
          f"({dropped / b77 * 100:.1f}%)", flush=True)
    print(f"  中枢数:  {z77} vs {z106}  差 {z106 - z77:+d}", flush=True)
    print(f"  信号数:  {s77} vs {s106}  差 {s106 - s77:+d}", flush=True)
    # 有多少笔会因第106课被丢弃
    short = sum(v for k, v in h77.items() if k < 6)
    print(f"  <6 K线的笔 = {short} / {b77} ({short / b77 * 100:.1f}%)", flush=True)

    # 牙齿验证（AGENTS.md §7）：必须证明注入真的生效
    if b106 == b77:
        print("\n⚠️ 警告：两种口径结果完全相同 —— 注入可能未生效！", flush=True)
        print("   已知陷阱：bi.py:269 在模块内直接调用 _can_form_bi，", flush=True)
        print("   猴子补丁 bi_mod._can_form_bi 无效。本脚本已改用源码重导入。", flush=True)
        print("   若仍相同，检查 analyser 是否走了别的笔路径。", flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
