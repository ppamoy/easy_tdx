#!/usr/bin/env python3
"""验证缠论图分型 tooltip：悬停应能同时看到「顶分型」和「底分型」。

背景（用户反馈）：鼠标悬停显示都是底分型，没有顶分型。
根因：后端分型序列化字段是 `fx_type`，前端 ChanlunChart 读的是 `fx.type`，
字段名不匹配 → `fx.type` 恒为 undefined → 全被当成底分型（else 分支），
顶分型 series 无数据 → tooltip 永远显示「底分型」。修复：前端改读 `fx_type`。

行为级验证（DSH 纪律第 1 条：看真实渲染行为，不看 DOM 标志）：
- 打开回测页跑 chanlun，等缠论图渲染；
- 沿图表**可见区域**横向扫描悬停，抓真实 tooltip 文本（ECharts tooltip 是
  position:absolute、z-index:9999999 的无 class div）；
- 断言 tooltip 里既有「顶分型」也有「底分型」。

用法：
    python3 scripts/verify_fx_tooltip.py
依赖：playwright（系统 chromium）
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _pw import import_playwright, launch_pw, ui_base  # noqa: E402

sync_api = import_playwright()

APP = os.environ.get("EASY_TDX_URL") or ui_base()
from _pw import chromium_path  # noqa: E402

CHROMIUM = chromium_path()
CODE = "000001"


def _read_tooltip(pg) -> str:
    """读当前可见的 ECharts tooltip 文本（真实渲染结果）。

    ECharts tooltip 特征：position:absolute、z-index:9999999、无 class、
    文本短（含日期 + O:... + 分型名）。
    """
    return pg.evaluate("""() => {
      let best = '';
      document.querySelectorAll('div').forEach(t => {
        const st = window.getComputedStyle(t);
        if (st.display === 'none' || st.visibility === 'hidden') return;
        if (st.position !== 'absolute') return;
        const txt = (t.innerText || '').trim();
        if (!txt || txt.length > 200) return;
        if (txt.includes('O:') || txt.includes('分型')) {
          if (txt.length > best.length) best = txt;
        }
      });
      return best;
    }""")


def main() -> int:
    with sync_api.sync_playwright() as pw:
        browser = launch_pw(pw)
        # 视口加高，保证图表完整可见（图表可能高于默认 900）
        pg = browser.new_page(viewport={"width": 1600, "height": 1200})
        try:
            pg.goto(APP, wait_until="domcontentloaded", timeout=45000)
            pg.wait_for_timeout(3000)
            pg.locator('input[placeholder="6位代码（市场自动识别）"]').first.fill(CODE)
            pg.locator("select").nth(1).select_option("chanlun")
            pg.locator("button", has_text="开始回测").first.click()
            # 轮询等图渲染（TDX 拉取耗时波动大，固定 sleep 会偶发误判）
            try:
                pg.wait_for_selector(".chanlun-chart canvas", timeout=90000)
            except Exception:
                print("❌ 等待 .chanlun-chart canvas 超时（90s），图未渲染")
                return 1
            pg.wait_for_timeout(2000)  # 等首帧绘制稳定

            canvas = pg.locator(".chanlun-chart canvas").first
            if canvas.count() == 0:
                print("❌ 找不到缠论图 canvas，图未渲染")
                return 1
            box = canvas.bounding_box()
            if not box:
                print("❌ 拿不到 canvas 位置")
                return 1
            vh = 1200
            # 只扫视口内可见部分（超出视口 mouse.move 无效）
            y_lo = max(box["y"] + 10, 0)
            y_hi = min(box["y"] + box["height"] - 10, vh)

            seen: dict[str, str] = {}
            n = 70
            for i in range(n):
                x = box["x"] + box["width"] * (0.03 + 0.94 * i / (n - 1))
                for yfrac in (0.25, 0.5, 0.75):
                    y = y_lo + (y_hi - y_lo) * yfrac
                    pg.mouse.move(x, y)
                    pg.wait_for_timeout(150)
                    tip = _read_tooltip(pg)
                    for kind in ("顶分型", "底分型"):
                        if kind in tip and kind not in seen:
                            seen[kind] = tip.replace("\n", " | ")[:120]
                if len(seen) == 2:
                    break

            print(f"tooltip 实际出现的分型类型: {sorted(seen.keys())}")
            for k in sorted(seen):
                print(f"  [{k}] 样例: {seen[k]}")

            if seen.keys() == {"顶分型", "底分型"}:
                print("✅ tooltip 同时出现「顶分型」和「底分型」→ 字段名不匹配已修复")
                return 0
            missing = {"顶分型", "底分型"} - set(seen.keys())
            print(f"❌ tooltip 缺少 {sorted(missing)} → 仍有问题")
            return 1
        finally:
            browser.close()


if __name__ == "__main__":
    sys.exit(main())
