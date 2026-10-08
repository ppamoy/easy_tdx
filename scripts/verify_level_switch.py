#!/usr/bin/env python3
"""级别切换一致性：切到递归级别（xd 等）时，图上结构必须整体同源。

要防的 bug：切换到 xd/xd_lN 递归级别后，笔/中枢正确换成了该级别的数据，
但**分型仍停留在 bi 级别**（后端 `levels` 里根本没有分型字段）。用户会看到
「按 xd 的笔划分、却标着 bi 的分型」这种自相矛盾的图。

同时验证反向：切回 bi 时分型必须**恢复**（曾经修完清空忘了恢复，导致永久丢失）。

为什么数 markLine 而不是 series.data：ChanlunChart 的笔/线段 series 的 `data`
恒为空（画在 markLine.data 里），中枢在 markArea.data。数 data 会得到 0 而误判。

用法：
    python3 scripts/verify_level_switch.py            # 三个页面都测
    python3 scripts/verify_level_switch.py --page chanlun

退出码：0=一致，1=发现不一致，2=环境/页面未就绪
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _pw import import_playwright, launch_pw, ui_base  # noqa: E402

# 每个 series 该怎么数
JS = """() => {
  const c = window.__CHANLUN_CHART__;
  if (!c) return null;
  const o = c.getOption && c.getOption();
  if (!o) return null;  // 实例已建但 option 还没算好（异步），别当成 0 数据
  const cnt = n => { const s = (o.series||[]).find(x => x.name === n);
                     return s ? (s.data||[]).length : 0; };
  const ml = n => { const s = (o.series||[]).find(x => x.name === n);
                    return (s && s.markLine) ? (s.markLine.data||[]).length : 0; };
  return { bis: ml('笔(虚线)'), ding: cnt('顶分型'), di: cnt('底分型') };
}"""

SELECT_TIMEOUT = 180000


def find_level_select(pg):
    """在所有页面中定位「分析级别」下拉（按 option 含 'xd' 识别，而非写死序号）。"""
    for i in range(pg.locator("select").count()):
        s = pg.locator("select").nth(i)
        try:
            vals = [o.get_attribute("value") for o in s.locator("option").all()]
        except Exception:  # noqa: BLE001
            continue
        if "bi" in vals and "xd" in vals:
            return s
    return None


def wait_chart(pg, timeout_ms: int = 90000) -> bool:
    """等缠论图真的渲染出来（有 canvas 且有 series）。"""
    elapsed = 0
    while elapsed < timeout_ms:
        r = pg.evaluate(JS)
        if r and (r["bis"] or r["ding"] or r["di"]):
            return True
        pg.wait_for_timeout(3000)
        elapsed += 3000
    return pg.evaluate("() => !!window.__CHANLUN_CHART__") is True


def audit_levels(pg, name: str) -> tuple[bool | None, str]:
    """单页：bi → xd → bi 往返检查。"""
    sel = find_level_select(pg)
    if sel is None:
        return None, f"{name}: 找不到「分析级别」下拉（页面结构变了？）"
    bi = pg.evaluate(JS)
    if not bi:
        return False, f"{name}: 图表未渲染出数据"

    sel.select_option("xd")
    pg.wait_for_timeout(6000)
    xd = pg.evaluate(JS)
    sel.select_option("bi")
    pg.wait_for_timeout(6000)
    back = pg.evaluate(JS)

    print(f"  bi:  笔={bi['bis']} 顶={bi['ding']} 底={bi['di']}")
    print(f"  xd:  笔={xd['bis']} 顶={xd['ding']} 底={xd['di']}")
    print(f"  回bi: 笔={back['bis']} 顶={back['ding']} 底={back['di']}")

    errs: list[str] = []
    # 数据不足时不该判失败——那是「没能说服自己」而非「发现不一致」。
    # 例如 train 页随机出题可能只给 2 根笔的窗口，此时任何对比都无意义。
    if bi["bis"] < 3 or not (bi["ding"] or bi["di"]):
        return None, f"{name}: 笔级别数据不足（笔={bi['bis']}）"
    if xd["bis"] == bi["bis"]:
        errs.append("切到 xd 后笔数量没变 —— 级别切换未生效")
    if xd["ding"] or xd["di"]:
        errs.append(
            f"切到 xd 后仍显示 bi 级别的分型（顶{xd['ding']}/底{xd['di']}）"
            "—— 后端 levels 无分型字段，应清空"
        )
    if back["bis"] != bi["bis"] or back["ding"] != bi["ding"]:
        errs.append("切回 bi 后未完全恢复（分型永久丢失？）")
    return (not errs, "; ".join(errs))


def page_chanlun(pg) -> bool:
    pg.goto(ui_base() + "/learn?tab=analysis", wait_until="domcontentloaded", timeout=45000)
    pg.wait_for_timeout(5000)
    pg.locator("button", has_text="开始分析").first.click()
    return wait_chart(pg)


def page_backtest(pg) -> bool:
    """回测页：填代码 → 选 chanlun 策略 → 开始回测 → 出缠论图。"""
    pg.goto(ui_base() + "/", wait_until="domcontentloaded", timeout=45000)
    pg.wait_for_timeout(4000)
    pg.locator('input[placeholder*="代码"]').first.fill("000001")
    # 策略下拉异步填充（选项来自后端），必须等它真的有选项再选
    for i in range(pg.locator("select").count()):
        s = pg.locator("select").nth(i)
        for _ in range(30):
            try:
                if s.locator("option").count() > 1:
                    break
            except Exception:  # noqa: BLE001
                break
            pg.wait_for_timeout(1000)
        vals = []
        try:
            vals = [o.get_attribute("value") for o in s.locator("option").all()]
        except Exception:  # noqa: BLE001
            continue
        # 必须选会画缠论结构图的策略（BacktestView 的
        # CHANLUN_STRUCTURED_STRATEGIES = {chanlun, chanlun_pair}）；
        # 像 changying_chanlun 虽含 "chanlun" 但不出图，模糊匹配会误选。
        hit = next((v for v in vals if v in ("chanlun", "chanlun_pair")), None)
        if hit:
            s.select_option(hit)
            break
    pg.locator("button", has_text="开始回测").first.click()
    return wait_chart(pg, SELECT_TIMEOUT)


def page_screening(pg) -> bool:
    """选股页：开始选股 → 点结果行触发缠论分析。"""
    pg.goto(ui_base() + "/screening", wait_until="domcontentloaded", timeout=45000)
    pg.wait_for_timeout(4000)
    try:
        pg.locator("button", has_text="开始选股").first.click()
    except Exception:  # noqa: BLE001
        return False
    pg.wait_for_timeout(4000)
    try:
        pg.wait_for_selector(".stock-item", timeout=SELECT_TIMEOUT)
    except Exception:  # noqa: BLE001
        return False
    try:
        pg.locator(".stock-item").first.click()
    except Exception:  # noqa: BLE001
        return False
    return wait_chart(pg, SELECT_TIMEOUT)


def page_train(pg) -> bool:
    """盘感训练页：**刻意排除**在自动级别切换验证之外。

    实测该页出题窗口固定在 36 根 K 线左右（盘感训练要用小窗口），
    因此只有 2 根笔；切到 xd 后笔数量不会变化，与本脚本要验证的
    「笔随级别切换」不符。这里不是产品缺陷，是页面定位不同。
    该页的分型清空/恢复逻辑改由静态契约 verify_fx_contract.py 覆盖。
    """
    return False


def page_verify_signal(pg) -> bool:
    """买卖点实证页：通常由信号详情页进入，这里走 signals 列表首个信号。"""
    pg.goto(ui_base() + "/learn?tab=verify", wait_until="domcontentloaded", timeout=45000)
    pg.wait_for_timeout(5000)
    # 列表里的「详情」/「查看」按钮会载入单股缠论图
    for t in ("详情", "查看", "明细"):
        try:
            btn = pg.locator("button", has_text=t).first
            if btn.count() and btn.is_visible():
                btn.click()
                break
        except Exception:  # noqa: BLE001
            continue
    return wait_chart(pg, SELECT_TIMEOUT)


PAGES = {
    "chanlun": page_chanlun,
    "backtest": page_backtest,
    "screening": page_screening,
    "verify": page_verify_signal,
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--page", choices=sorted(PAGES) + ["train"], action="append")
    args = ap.parse_args()
    # train 页默认不跑（窗口太短，见 page_train 说明）；显式指定才执行
    drivers = {**PAGES, "train": page_train}
    names = args.page or sorted(PAGES)
    PAGES.update(drivers)

    sync = import_playwright()
    failures: list[str] = []
    skipped: list[str] = []
    with sync.sync_playwright() as pw:
        browser = launch_pw(pw)
        try:
            for name in names:
                pg = browser.new_page(viewport={"width": 1600, "height": 1200})
                try:
                    if not PAGES[name](pg):
                        skipped.append(f"{name}: 未自动渲染出缠论图（需人工交互）")
                        print(f"⚠️  [{name}] 未自动渲染出缠论图")
                        continue
                    ok, why = audit_levels(pg, name)
                    if ok is None:  # 数据不足 / 前置条件不满足
                        skipped.append(why)
                        print(f"⚠️  {why}")
                    elif ok:
                        print(f"✅ [{name}] 级别切换一致")
                    else:
                        print(f"❌ [{name}] {why}")
                        failures.append(f"[{name}] {why}")
                finally:
                    pg.close()
        finally:
            browser.close()

    if failures:
        print("\n失败项：")
        for f in failures:
            print(f"  · {f}")
        return 1
    if skipped:
        print("\n跳过项（非失败）：")
        for s in skipped:
            print(f"  · {s}")
        return 2
    print("\n✅ 所有页面的级别切换均一致")
    return 0


if __name__ == "__main__":
    sys.exit(main())
