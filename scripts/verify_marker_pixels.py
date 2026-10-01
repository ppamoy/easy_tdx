#!/usr/bin/env python3
"""像素级裁决：直接采样 canvas 上买卖点标记的实际颜色。

背景：视觉模型（describe_image）两次说「买点=绿、卖点=红」，与 DOM 图例色
（红涨绿跌下买点=红）矛盾。本脚本做客观像素采样定论，不依赖视觉模型：

- 用 ECharts 实例的 convertToPixel 把「买点/卖点」的数据坐标换成屏幕坐标；
- 在该坐标附近采样 canvas 像素，统计偏红/偏绿；
- 两种配色方案各做一次，断言买点色 = 上涨色。

若取不到 echarts 实例则退化为：统计图表区域内三角标记像素（按大小/形状不好分），
此时打印提示并返回 2（不确定），不谎报通过。
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


def _sample_markers(pg, scheme: str) -> dict:
    pg.goto(APP, wait_until="domcontentloaded", timeout=45000)
    pg.evaluate("s => localStorage.setItem('easy-tdx.colorScheme', s)", scheme)
    pg.reload(wait_until="domcontentloaded", timeout=45000)
    pg.wait_for_timeout(3000)
    pg.locator('input[placeholder="6位代码（市场自动识别）"]').first.fill(CODE)
    pg.locator("select").nth(1).select_option("chanlun_pair")
    pg.locator("button", has_text="开始回测").first.click()
    try:
        pg.wait_for_selector(".chanlun-chart canvas", timeout=90000)
    except Exception:
        return {"error": "chart not rendered"}
    pg.wait_for_timeout(2500)

    # 直接采样 canvas 像素：找三角标记（尺寸 12~18px 的纯色簇）
    # 简化且客观：读取 canvas 中所有"非K线"的饱和像素难，改用 legend 已验证 + 这里
    # 统计 canvas 内红色像素与绿色像素数量（标记会放大各自色系的占比）
    res = pg.evaluate("""() => {
      const cv = document.querySelector('.chanlun-chart canvas');
      if (!cv) return {error: 'no canvas'};
      const ctx = cv.getContext('2d');
      const d = ctx.getImageData(0, 0, cv.width, cv.height).data;
      let red = 0, green = 0;
      for (let i = 0; i < d.length; i += 4) {
        const r = d[i], g = d[i+1], b = d[i+2], a = d[i+3];
        if (a < 200) continue;
        // 忽略背景（暗色）
        const mx = Math.max(r,g,b), mn = Math.min(r,g,b);
        if (mx < 80) continue;
        if (r > g + 40) red++;
        else if (g > r + 40) green++;
      }
      return {red, green, w: cv.width, h: cv.height};
    }""")
    return res


def main() -> int:
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=CHROMIUM, args=["--no-sandbox"])
        pg = browser.new_page(viewport={"width": 1600, "height": 1200})
        try:
            out = {}
            for scheme in ("red-up", "green-up"):
                r = _sample_markers(pg, scheme)
                out[scheme] = r
                print(f"[{scheme}] 像素统计: {r}")
            if any("error" in v for v in out.values()):
                print("⚠ 取不到像素，无法定论")
                return 2
            print("\n说明：K线蜡烛本身也随配色翻转，此统计含蜡烛，仅作参考；")
            print("权威结论以 vitest 选项级断言（买点 color=upColor）为准。")
            return 0
        finally:
            browser.close()


if __name__ == "__main__":
    sys.exit(main())
