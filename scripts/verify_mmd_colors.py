#!/usr/bin/env python3
"""验证买卖点配色跟随全局涨跌配色（红涨绿跌→买点红、卖点绿；反之亦然）。

行为级：切两种配色方案各渲染一次，截图存盘供视觉核对；同时读图例 span 的
**computed 颜色**（v-bind 绑定到 upColor/downColor，能反映当前配色）。

用法：
    python3 scripts/verify_mmd_colors.py
依赖：playwright（系统 chromium）
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _pw import import_playwright, ui_base  # noqa: E402

sync_api = import_playwright()

APP = os.environ.get("EASY_TDX_URL") or ui_base()
from _pw import chromium_path  # noqa: E402

CHROMIUM = chromium_path()
CODE = "000001"


def _run(pg, scheme: str) -> dict:
    """用指定配色方案跑一次回测，返回图例实际渲染色。"""
    pg.goto(APP, wait_until="domcontentloaded", timeout=45000)
    # 先设配色再加载页（colors.ts 从 localStorage 读）
    pg.evaluate(
        "s => localStorage.setItem('easy-tdx.colorScheme', s)",
        scheme,
    )
    pg.reload(wait_until="domcontentloaded", timeout=45000)
    pg.wait_for_timeout(3000)
    pg.locator('input[placeholder="6位代码（市场自动识别）"]').first.fill(CODE)
    pg.locator("select").nth(1).select_option("chanlun_pair")
    pg.locator("button", has_text="开始回测").first.click()
    # 轮询等图渲染（TDX 拉取耗时波动大，固定 sleep 会偶发误判）
    try:
        pg.wait_for_selector(".chanlun-chart canvas", timeout=90000)
    except Exception:
        print("❌ 等待 .chanlun-chart canvas 超时（90s）")
        raise
    pg.wait_for_timeout(2000)

    # 读图例里买点/卖点的 computed 颜色（v-bind 绑定，反映真实配色）
    colors = pg.evaluate("""() => {
      const pick = (cls) => {
        const el = document.querySelector('.mmd-legend .ic.' + cls);
        if (!el) return null;
        return window.getComputedStyle(el).color;
      };
      return {
        buy1: pick('buy-1'),
        buy3: pick('buy-3'),
        sell1: pick('sell-1'),
        sell3: pick('sell-3'),
      };
    }""")
    return colors


def main() -> int:
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=CHROMIUM, args=["--no-sandbox"])
        pg = browser.new_page(viewport={"width": 1600, "height": 1200})
        try:
            results = {}
            for scheme, label in (("red-up", "红涨绿跌"), ("green-up", "绿涨红跌")):
                c = _run(pg, scheme)
                results[scheme] = c
                print(f"[{scheme} / {label}] 图例色: {c}")
                pg.screenshot(path=f"/tmp/mmd_{scheme}.png")
                print(f"  截图 /tmp/mmd_{scheme}.png")

            # 断言：买点色 = 上涨色，卖点色 = 下跌色
            RED = "rgb(239, 65, 70)"      # #ef4146
            GREEN = "rgb(24, 160, 88)"    # #18a058
            ok = True
            # 红涨绿跌：买点应红、卖点应绿
            red = results["red-up"]
            if red["buy1"] != RED or red["sell1"] != GREEN:
                print(
                    "❌ 红涨绿跌下买/卖点色不符: "
                    f"买={red['buy1']} 卖={red['sell1']}"
                )
                ok = False
            # 绿涨红跌：买点应绿、卖点应红
            green = results["green-up"]
            if green["buy1"] != GREEN or green["sell1"] != RED:
                print(
                    "❌ 绿涨红跌下买/卖点色不符: "
                    f"买={green['buy1']} 卖={green['sell1']}"
                )
                ok = False
            # 两种方案下买点色必须不同（证明真的跟随切换，而非写死）
            if results["red-up"]["buy1"] == results["green-up"]["buy1"]:
                print("❌ 切换配色后买点色不变 → 未跟随涨跌配色")
                ok = False

            if ok:
                print("✅ 买点=上涨色、卖点=下跌色，且切换配色后随之变化")
                return 0
            return 1
        finally:
            browser.close()


if __name__ == "__main__":
    sys.exit(main())
