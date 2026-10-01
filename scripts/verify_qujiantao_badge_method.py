#!/usr/bin/env python3
"""渲染验证：区间套徽章是否真的按**口径**区分（V731）。

背景（实测确认的误导链）：
- analyser.py 把 qujiantao_for_result（**递归级别**，method='recursive'）的
  结果写进 mmd._qujiantao；
- 前端据此渲染徽章，但改前只用 nested，一律显示「🔗 套」+ qt-ok；
- 而 docs/区间套现状说明与统一方案.md §七 实测：递归确认率 **3%**，
  真实双周期 **50%**，文档明确"不得用于区间套过滤"。

即：用户看到的「🔗 套」其实是"高一级别趋势参考"，却呈现得像原文意义的
区间套已确认。本脚本验证改后两种口径在**真实渲染**里看得出来区别。

按 AGENTS.md 纪律：渲染类改动必须**真看渲染结果**（截图 + 图像模型），
不能只数 DOM 节点或断言请求 200。

用法（需先起前端 3012）：
    python3 scripts/verify_qujiantao_badge_method.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _pw import chromium_path, import_playwright, ui_base  # noqa: E402

UI = os.environ.get("EASY_TDX_UI", "http://127.0.0.1:3012")
OUT = "/tmp/qt_badge_method.png"

# 注入两个信号：同一 nested=true，只有 method 不同 → 徽章必须不同
ANALYZE = {
    "mmds": [
        {
            "type": "1buy", "date": "2025-06-10 00:00:00", "msg": "一买(真实双周期)",
            "confidence": 0.7, "bar_index": 100,
            "qujiantao": {
                "nested": True, "score": 0.8, "method": "cross_period",
                "confidence_adjust": 0.0,
                "msg": "区间套确认 | 低周期窗口内出现同方向底背驰(买)确认",
            },
        },
        {
            "type": "2buy", "date": "2025-07-01 00:00:00", "msg": "二买(递归级别)",
            "confidence": 0.6, "bar_index": 130,
            "qujiantao": {
                "nested": True, "score": 0.8, "method": "recursive",
                "confidence_adjust": 0.0,
                "msg": "区间套确认 | 低级别窗口内出现同方向底背驰(买)确认",
            },
        },
    ],
    "fractals": [], "valid_fractals": [], "bis": [], "xds": [], "zss": [],
    "bcs": [], "levels": [],
}


def main() -> int:
    pw = import_playwright()
    with pw.sync_playwright() as p:
        b = p.chromium.launch(executable_path=chromium_path(), args=["--no-sandbox"])
        pg = b.new_page(viewport={"width": 1600, "height": 900})

        # 拦截：bars 走合成（800 根），analyze 走注入
        def _route(route):
            u = route.request.url
            if "/chanlun/analyze" in u:
                route.fulfill(status=200, content_type="application/json",
                              body=__import__("json").dumps(ANALYZE))
            elif "/bars" in u or "/kline" in u:
                import json
                bars = [
                    {
                        "datetime": f"2025-{1 + (i // 28) % 12:02d}-{1 + i % 28:02d}T15:00:00",
                        "open": 10.0, "close": 10.0, "high": 10.5, "low": 9.5,
                        "vol": 1000, "amount": 10000.0,
                    }
                    for i in range(800)
                ]
                # /bars 响应是 {data: [...]}（前端 body.data.map，裸数组会报
                # "Cannot read properties of undefined (reading 'map')"）
                route.fulfill(status=200, content_type="application/json",
                              body=json.dumps({"data": bars}))
            else:
                route.continue_()

        pg.route("**/api/**", _route)
        pg.route("**/chanlun/**", _route)

        pg.goto(f"{UI}/chanlun", wait_until="domcontentloaded")
        pg.wait_for_timeout(4000)

        # 触发分析（有的版本自动跑）
        try:
            btn = pg.locator("button", has_text="分析")
            if btn.count() > 0:
                btn.first.click()
                pg.wait_for_timeout(3000)
        except Exception:
            pass
        pg.wait_for_timeout(2500)

        badges = pg.locator(".qt-badge")
        n = badges.count()
        print(f"徽章数量: {n}")
        results = []
        for i in range(n):
            cls = badges.nth(i).get_attribute("class") or ""
            txt = (badges.nth(i).inner_text() or "").strip()
            title = badges.nth(i).get_attribute("title") or ""
            print(f"  [{i}] class={cls!r} text={txt!r}")
            print(f"       title前60={title[:60]!r}")
            results.append((cls, txt, title))

        pg.screenshot(path=OUT)
        print(f"\n整页截图: {OUT}")
        # 元素级截图：整页截图里徽章很小/可能在折叠区，直接截徽章本身，
        # 保证「真看到渲染结果」而不是靠 DOM 属性推断。
        for i in range(n):
            try:
                badges.nth(i).scroll_into_view_if_needed()
                badges.nth(i).screenshot(path=f"/tmp/qt_badge_{i}.png")
                print(f"  徽章[{i}] 元素截图: /tmp/qt_badge_{i}.png")
            except Exception as e:
                print(f"  徽章[{i}] 截图失败: {e}")
        # 拼成一张对比图，便于一次看完两种口径
        try:
            from PIL import Image
            ims = [Image.open(f"/tmp/qt_badge_{i}.png") for i in range(n)]
            w = max(i.width for i in ims); h = sum(i.height for i in ims) + 8 * (len(ims) - 1)
            canvas = Image.new("RGB", (w, h), (20, 24, 32))
            y = 0
            for i in ims:
                canvas.paste(i, (0, y)); y += i.height + 8
            canvas.save("/tmp/qt_badges_compare.png")
            print("  对比图: /tmp/qt_badges_compare.png")
        except Exception as e:
            print(f"  拼图失败: {e}")
        b.close()

    # 断言（行为级，不只是 DOM 存在）
    ok = True
    ok_cls = [r for r in results if "qt-ok" in r[0]]
    rec_cls = [r for r in results if "qt-recursive" in r[0]]
    print(f"\nqt-ok 徽章数: {len(ok_cls)}  qt-recursive 徽章数: {len(rec_cls)}")
    if len(ok_cls) < 1:
        print("❌ 没有 qt-ok（真实双周期）徽章")
        ok = False
    if len(rec_cls) < 1:
        print("❌ 没有 qt-recursive（递归级别）徽章 —— 口径未区分")
        ok = False
    if ok_cls and "🔗 套" not in ok_cls[0][1]:
        print(f"❌ qt-ok 文字不对: {ok_cls[0][1]!r}")
        ok = False
    if rec_cls and "🔗 级?" not in rec_cls[0][1]:
        print(f"❌ qt-recursive 文字不对: {rec_cls[0][1]!r}")
        ok = False
    if rec_cls and "非真跨周期" not in rec_cls[0][2]:
        print(f"❌ 递归口径 title 缺来源警告: {rec_cls[0][2][:60]!r}")
        ok = False

    print("\n结论:", "✅ 口径已区分" if ok else "❌ 未区分")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
