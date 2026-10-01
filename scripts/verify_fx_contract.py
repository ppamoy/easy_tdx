#!/usr/bin/env python3
"""契约一致性巡检：凡是渲染缠论图的页面，都必须传 validFxs。

要防的回归（已经发生过一次）：某页面只传了原始 `fractals`，而 `fractals` 是
find_fractals 逐三根滑动窗口的产物，含大量共用K线的重叠分型——图上就会出现
「底分型紧跟着顶分型」这种不符合缠论原文的标注。

因此约定：**任何使用 ChanlunChart 的地方都必须传 :validFxs**。本脚本静态检查
这一点，作为 CI 的廉价前置闸门（真正的渲染正确性由 verify_fx_pages.py 保证）。

同时检查后端：凡是往响应里塞 `fractals` 的路由，都应一并给 `valid_fractals`，
否则前端拿不到干净数据源。

用法：
    python3 scripts/verify_fx_contract.py

退出码：0=一致，1=发现漏传
"""

from __future__ import annotations

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VIEWS_DIR = os.path.join(ROOT, "web-ui", "src", "views")
ROUTERS_DIR = os.path.join(ROOT, "src", "easy_tdx", "web", "routers")

# 前端图表消费的结构字段全集。任何路由函数里赋值过这些字段，返回时就不得
# 在手工字段清单里漏掉（train/session 曾漏 valid_fractals，盘感训练页整页 0 分型）。
STRUCTURE_FIELDS = ("bis", "xds", "zss", "mmds", "fractals", "valid_fractals",
                    "bcs", "boll", "bars", "zsds", "qsds", "macd")

# 前端图表真正消费的 to_dict 图表字段（levels 是递归级别，另有 _level_payload
# 专用契约；*_count 是统计数字，页面标题用，漏了会退化但不至于图错）。
CHART_CONSUMED = frozenset({"bis", "xds", "zss", "zsds", "qsds", "mmds", "bcs", "macd"})


def check_views() -> list[str]:
    """检查所有用 ChanlunChart 的页面都传了 validFxs。"""
    errs: list[str] = []
    if not os.path.isdir(VIEWS_DIR):
        return [f"目录不存在: {VIEWS_DIR}"]
    for fn in sorted(os.listdir(VIEWS_DIR)):
        if not fn.endswith(".vue"):
            continue
        src = open(os.path.join(VIEWS_DIR, fn), encoding="utf-8").read()
        if "ChanlunChart" not in src:
            continue
        fxs_n = len(re.findall(r":fxs\s*=", src))
        valid_n = len(re.findall(r":validFxs\s*=", src))
        if fxs_n and not valid_n:
            errs.append(f"{fn}: 传了 :fxs 但没传 :validFxs —— 会渲染脏分型")
        elif fxs_n > valid_n:
            errs.append(f"{fn}: :fxs 出现 {fxs_n} 次但 :validFxs 只有 {valid_n} 次 —— 有实例漏传")
    return errs


def _bound_var(expr: str) -> str:
    """从模板绑定表达式里取出 ref 变量名。

    绑定形式在仓库里并不统一，见过：
        :validFxs="validFxs"                                -> validFxs
        :validFxs="validFxs as any"                         -> validFxs
        :validFxs="(selected.valid_fractals as any) ?? []"  -> selected.valid_fractals
    需剥掉 TS 类型断言、括号和兜底表达式，只取首个标识符（含 . 的成员路径）。
    """
    e = re.sub(r"\s*as\s+any\s*", "", expr)
    e = e.strip().strip("()")
    e = e.split("??")[0].strip().strip("()")
    m = re.search(r"[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*", e)
    return m.group(0) if m else ""


def _level_payload_fields() -> set[str]:
    """从后端 _level_payload 的返回里解析出有哪些 key。

    不写死名单：改名/增删字段时这里会自动跟上。
    """
    path = os.path.join(ROOT, "src", "easy_tdx", "chanlun", "analyser.py")
    if not os.path.isfile(path):
        return set()
    src = open(path, encoding="utf-8").read()
    m = re.search(r"def _level_payload\(", src)
    if not m:
        return set()
    tail = src[m.end():]
    ret = tail.find("return {")
    if ret < 0:
        return set()
    nxt = re.search(r"\n    def ", tail[ret:])
    body = tail[ret:ret + nxt.start()] if nxt else tail[ret:]
    return set(re.findall(r'"([a-z_]+)":', body))


def check_level_payload_shift() -> list[str]:
    """前端平移 levels 里的字段时，不能平移后端压根没给的字段（死代码）。

    后端 `levels` 每级只给 bis/xds/zss/mmds/bcs/zsds/qsds 等；这里没有分型。
    之前 StockPickView 却在平移 `lv.fractals` / `lv.valid_fractals` —— 恒为空
    的死代码，会造成「这里处理过分型」的错觉，掩盖真实缺口。
    """
    errs: list[str] = []
    backend = _level_payload_fields()
    if not backend:
        errs.append("无法从 analyser._level_payload 解析字段（解析失败，非产品问题）")
        return errs
    for fn in sorted(os.listdir(VIEWS_DIR)):
        if not fn.endswith(".vue"):
            continue
        src = open(os.path.join(VIEWS_DIR, fn), encoding="utf-8").read()
        for m in re.finditer(r"([a-z_]+)\s*:\s*\w+\(\s*(?:lv|lvl)\.([a-z_]+)", src):
            if m.group(2) not in backend:
                errs.append(
                    f"{fn}: 平移了 levels 里不存在的字段 `{m.group(2)}`"
                    f" （后端只给 {sorted(backend)}）—— 是恒为空的死代码"
                )
    return errs


def check_return_drops_structure_fields() -> list[str]:
    """路由函数里算过的结构字段，不得在 return 的手工字段清单里漏掉。

    这类 bug 已实际发生过多次：字段在函数中途 `d["valid_fractals"] = ...` 配套
    算好，但结尾 `return _to_json_safe({ "fractals": ..., ... })` 手工列字段时
    漏掉它 —— 前端拿到的恒为空（train/session 曾漏 valid_fractals 致整页
    0 分型、漏 levels 致线段切换空图、漏 macd 致副图缺失）。

    建模边界（经坏例回归校准）：
    - 抓：本函数体内 `d["field"] = ...` 引号键赋值过、return 却是手工 dict
      字面量且漏了该字段（多次真实事故均属此类）。
    - 不抓：字段经 `d = result.to_dict()` 整体流入（如 mmds/bis——赋值发生在
      analyser.to_dict 里，本函数只是搬运）；`d.pop(...)` 这类显式变换；
      局部变量流转（如 `"bars": bars` 引用局部 list）。这些需要跨函数
      数据流分析，会误伤合法的子集返回端点（如 recommend 决策卡片），
      故刻意不建模；to_dict 流入类由下面的正向覆盖检查兜住。
    """
    errs: list[str] = []
    if not os.path.isdir(ROUTERS_DIR):
        return errs
    for fn in sorted(os.listdir(ROUTERS_DIR)):
        if not fn.endswith(".py"):
            continue
        path = os.path.join(ROUTERS_DIR, fn)
        src = open(path, encoding="utf-8").read()
        if not any(f'"{f}"' in src for f in STRUCTURE_FIELDS):
            continue
        # 按 def 分块，两遍扫描，边界各异：嵌套 def（4空格缩进）会把外层
        # 函数拦腰截断、丢掉 return 块造成误报，必须分开扫。
        # ① 模块级函数：边界 = 下一个模块级 def；
        # ② 嵌套组装函数（如 multi_level 的 fmt_result）：整段构建返回 dict，
        #    漏字段最容易藏在这里；边界 = 下一个 4 缩进的 def。
        scans = (
            # (本层 def 的匹配、下一边界 def 的匹配)
            (r"^(?:async )?def (\w+)\(", r"^(?:async )?def \w+\("),
            (r"^(    )(?:async )?def (\w+)\(", r"^    (?:async )?def \w+\("),
        )
        for def_pat, nxt_pat in scans:
            for m in re.finditer(def_pat, src, re.M):
                start = m.start()
                nxt = re.search(nxt_pat, src[m.end():], re.M)
                body = src[start: m.end() + nxt.start()] if nxt else src[start:]
                # 合格的引用方式有三种：手工字段清单（"field":）、**d 展开、
                # 或整个 `return d`。三者任一都不算漏。
                spread = len(re.findall(r"\*\*\w*\b", body))
                # 只认「return d」「return result」这类整体返回（词边界收严，
                # 别把 return round(...) 里的 round 当成 d）
                whole = len(re.findall(r"\breturn\s+[a-z_]{1,12}\b(?!\s*\()", body))
                if spread or whole:
                    continue
                for f in STRUCTURE_FIELDS:
                    assigns = len(re.findall(rf'["\']{f}["\']\s*\]?\s*=', body))
                    if not assigns:
                        continue
                    manual = len(re.findall(rf'["\']{f}["\']\s*:', body))
                    if manual == 0:
                        errs.append(
                            f"{fn}.{m.group(1) or m.group(2)}: 给 {f} 赋了值，但返回的"
                            "手工字段清单里没有它 —— 前端将拿到恒为空的数据"
                        )

                # 正向检查：手工清单端点若搬运结构数据（含 "bis"/"fractals" 等键），
                # 必须覆盖 to_dict 的全部图表字段。macd 曾被这样漏掉（train 页
                # MACD 副图恒缺失），它经 to_dict 整体流入，上面的赋值检查抓不到。
                manual_keys = set(re.findall(r'"([a-z_]+)"\s*:', body))
                struct_in_body = manual_keys & (set(STRUCTURE_FIELDS) - {"boll", "macd"})
                if not struct_in_body:
                    continue
                missing = _to_dict_chart_fields() & CHART_CONSUMED - manual_keys
                if missing:
                    errs.append(
                        f"{fn}.{m.group(1) or m.group(2)}: 手工返回清单搬运了结构数据"
                        f"（{sorted(struct_in_body)}），但漏了 to_dict 的图表字段"
                        f" {sorted(missing)} —— 消费端将拿到恒为空的数据"
                    )
    return errs


def _to_dict_chart_fields() -> set[str]:
    """解析 ChanlunResult.to_dict 的顶层字段集。"""
    path = os.path.join(ROOT, "src", "easy_tdx", "chanlun", "analyser.py")
    if not os.path.isfile(path):
        return set()
    src = open(path, encoding="utf-8").read()
    m = re.search(r"def to_dict\(self\)", src)
    if not m:
        return set()
    nxt = re.search(r"    def [a-z_]+\(self", src[m.end():])
    body = src[m.start():m.end() + nxt.start()] if nxt else src[m.start():]
    return set(re.findall(r'^            "([a-z_]+)":', body, re.M))


def check_level_switch() -> list[str]:
    """切换递归级别（xd/xd_lN）时，分型必须同步清空，且切回 bi 要恢复。

    后端 `levels` 里没有分型字段（只有 bis/xds/zss/mmds/bcs）。若某个页面切到
    递归级别时不重设分型，图上就会出现「xd 的笔 + bi 的分型」这种自相矛盾的组合。

    为什么这里要**自动扫描**而不是列名单：之前列了 3 个页面的名单，结果漏了
    TrainView / SignalVerifyView（它们同样有 applyAnalysisLevel）——凡是靠手写
    名单的检查，一旦新增调用方就会静默失效。这里改为遍历所有含级别切换的页面，
    并从模板里的 :validFxs 绑定反推变量名，新增页面自动纳入。
    """
    errs: list[str] = []
    if not os.path.isdir(VIEWS_DIR):
        return errs

    for fn in sorted(os.listdir(VIEWS_DIR)):
        if not fn.endswith(".vue"):
            continue
        path = os.path.join(VIEWS_DIR, fn)
        src = open(path, encoding="utf-8").read()
        if "applyChanlunLevel" not in src and "applyAnalysisLevel" not in src:
            continue  # 该页没有级别切换，不适用

        # 从模板绑定反推变量名：:validFxs="xxx" → xxx.value
        binds = re.findall(r':validFxs\s*=\s*"([^"]+)"', src)
        if not binds:
            errs.append(f"{fn}: 有级别切换但没传 :validFxs —— 递归级别无从清空")
            continue
        valv = _bound_var(binds[0]) + ".value"

        cleared = len(re.findall(re.escape(valv) + r"\s*=\s*\[\]", src))
        if cleared == 0:
            errs.append(
                f"{fn}: 级别切换时没有清空 {valv} —— 递归级别会残留 bi 的分型"
            )
        # 恢复：切回 bi 分支应重新从 data 赋值（可能经 mapFx(s)() 包装）
        restored = len(
            re.findall(re.escape(valv) + r"\s*=\s*(?:mapFxs?\(\s*)?data\?", src)
        )
        if restored == 0:
            errs.append(
                f"{fn}: 切回笔级别时没从 data 恢复 {valv} —— 分型会永久丢失"
            )
    return errs


def check_routers() -> list[str]:
    """检查后端：给 fractals 的地方应同时给 valid_fractals。"""
    errs: list[str] = []
    if not os.path.isdir(ROUTERS_DIR):
        return [f"目录不存在: {ROUTERS_DIR}"]

    for fn in sorted(os.listdir(ROUTERS_DIR)):
        if not fn.endswith(".py"):
            continue
        path = os.path.join(ROUTERS_DIR, fn)
        src = open(path, encoding="utf-8").read()
        fx_assigns = len(re.findall(r'["\']fractals["\']\s*\]?\s*=', src))
        vf_assigns = len(re.findall(r'["\']valid_fractals["\']\s*\]?\s*=', src))
        if fx_assigns and not vf_assigns:
            errs.append(f"{fn}: 只给了 fractals({fx_assigns} 处) 没有 valid_fractals")
        elif fx_assigns > vf_assigns:
            errs.append(
                f"{fn}: fractals 赋值 {fx_assigns} 处但 valid_fractals 只有 {vf_assigns} 处"
            )
    return errs


def main() -> int:
    errs = (check_views() + check_routers() + check_level_switch()
            + check_level_payload_shift() + check_return_drops_structure_fields())
    if errs:
        print("❌ 契约不一致：")
        for e in errs:
            print("  ·", e)
        print("\n约定：展示层必须用 valid_fractals（笔端点分型），原始 fractals 仅供内部计算。")
        return 1
    print("✅ 契约一致：validFxs 已传 / valid_fractals 已给 / 级别切换同步分型")
    return 0


if __name__ == "__main__":
    sys.exit(main())
