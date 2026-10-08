#!/usr/bin/env python3
"""渲染验证：F9 α 卡片是否真的显示「n/总期数」口径（V731）。

按 AGENTS.md 纪律：渲染类改动必须**真看渲染结果**（截图 + 图像模型），
不能只数 DOM 节点或断言请求 200。

用法（需先起后端 8000 + 前端 3012）：
    python3 scripts/verify_f9_alpha_badge.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _pw import chromium_path, import_playwright, launch_pw  # noqa: E402

UI = os.environ.get("EASY_TDX_UI", "http://127.0.0.1:3012")

# 注入：3 个时点；20日/60日只有 2 期有效（1 期指数缺失），250日 3 期全有效
def _real_summary() -> dict:
    """用后端真实 _summarize_periods 产出 summary（避免手搓 mock 字段不全）。"""
    import sys as _sys

    _sys.path.insert(0, "/home/skp/workspace/easy_tdx/src")
    from datetime import date

    from easy_tdx.fundamental.pipeline import _summarize_periods

    def _row():
        return {"category": "tree",
                "performance": {"ret_20d": 5.0, "ret_60d": 12.0, "ret_250d": 30.0}}

    periods = [
        {"date": str(date(2026, 7, 20)), "results": [_row() for _ in range(3)],
         "index": {"ret_20d": 1.0, "ret_60d": 3.0, "ret_250d": 8.0}},
        {"date": str(date(2026, 8, 20)), "results": [_row() for _ in range(3)],
         "index": {"ret_20d": 1.0, "ret_60d": 3.0, "ret_250d": 8.0}},
        # 第 3 期 20 日指数缺失 ⇒ 20 日 α 应只基于 2 期
        {"date": str(date(2026, 9, 20)), "results": [_row() for _ in range(3)],
         "index": {"ret_20d": None, "ret_60d": 3.0, "ret_250d": 8.0}},
    ]
    return {"periods": periods, "summary": _summarize_periods(periods, (20, 60, 250))}


MOCK = _real_summary()

_UNUSED = {
    "periods": [
        {"date": "2026-07-20", "results": [], "index": {"ret_20d": 1.0, "ret_250d": 2.0}},
        {"date": "2026-08-20", "results": [], "index": {"ret_20d": 1.0, "ret_250d": 2.0}},
        {"date": "2026-09-20", "results": [], "index": {"ret_20d": None, "ret_250d": 2.0}},
    ],
    "summary": {
        # 前端会读 by_category[cat].count，缺了会抛
        "by_category": {
            cat: {
                "count": 3 if cat == "tree" else 0,
                **{
                    f"ret_{h}d": (
                        {"count": 3, "avg": 5.5 + h / 100, "hit_rate": 1.0}
                        if cat == "tree"
                        else {"count": 0, "avg": None, "hit_rate": None}
                    )
                    for h in (20, 60, 250)
                },
            }
            for cat in ("tree", "grain", "vegetable")
        },
        "overall": {"count": 3},
        "index": {"ret_20d": {"count": 2, "avg": 1.0}, "ret_250d": {"count": 3, "avg": 2.0}},
        "beats_index": {
            "ret_20d": {"alpha": 4.5, "beats": True, "n_periods": 2},
            "ret_60d": {"alpha": -1.2, "beats": False, "n_periods": 2},
            "ret_250d": {"alpha": 7.8, "beats": True, "n_periods": 3},
        },
    },
}


def main() -> int:
    api = import_playwright()
    with api.sync_playwright() as pw:
        b = launch_pw(pw)
        pg = b.new_page(viewport={"width": 1600, "height": 1400})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))

        routed = {"n": 0}

        def _handler(route):
            routed["n"] += 1
            route.fulfill(status=200, content_type="application/json",
                          body=__import__("json").dumps(MOCK))

        pg.route("**/fundamental/verify**", _handler)

        pg.goto(UI + "/fundamental", wait_until="domcontentloaded", timeout=60000)
        pg.wait_for_timeout(5000)

        # 切到「批量验证」模式并触发一次请求
        clicked = False
        for txt in ["批量验证", "验证", "时点验证"]:
            try:
                loc = pg.locator("button", has_text=txt).first
                if loc.count() and loc.is_visible():
                    loc.click()
                    clicked = True
                    break
            except Exception:
                continue
        pg.wait_for_timeout(3000)
        # 若有「开始验证」类按钮再点一次
        for txt in ["开始验证", "开始", "运行"]:
            try:
                loc = pg.locator("button", has_text=txt).first
                if loc.count() and loc.is_visible():
                    loc.click()
                    break
            except Exception:
                continue
        pg.wait_for_timeout(6000)

        print("routed 拦截次数:", routed["n"])
        print("点击模式按钮:", clicked)
        print("页面错误:", errors[:3])

        # 截 α 卡片区域（找不到就整页）
        card = pg.locator(".beats-card")
        if card.count() and card.first.is_visible():
            card.first.screenshot(path="/tmp/f9_card.png")
            print("已截 .beats-card")
        else:
            pg.screenshot(path="/tmp/f9_card.png", full_page=True)
            print("未找到 .beats-card，改为整页截图")
        b.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
