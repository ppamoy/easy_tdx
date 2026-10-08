#!/usr/bin/env python3
"""渲染验证 F2「逐笔复盘讲解」：切到复盘页后表格必须有数据（V731 回归）。

背景：训练会话带防作弊闸门时后端把 mmd_outcomes 置空；若前端不按模式补拉，
复盘表格（v-for outcomes）**永远是空的**，F2 直接失效 —— 这正是引入闸门
时的真实回归。本脚本起真实前后端，拦截 session 接口模拟两种响应，切到
「复盘讲解」tab 后截图，确认表格真的渲染出信号行。

按 AGENTS.md 纪律：渲染类验证必须**真看渲染结果**（截图 + 图像模型），
不能只断言 DOM 存在或请求 200。

用法（需先起后端 8000 + 前端 3012）：
    python3 scripts/verify_f2_review_panel.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _pw import chromium_path, import_playwright, launch_pw  # noqa: E402

UI = os.environ.get("EASY_TDX_UI", "http://127.0.0.1:3012")


def _bars(n: int = 160) -> list[dict]:
    out = []
    for i in range(n):
        c = 10 + (i % 40) * 0.1
        out.append({
            "datetime": f"2025-{(1 + i // 28) % 12 + 1:02d}-{(i % 28) + 1:02d}T15:00:00",
            "open": c, "close": c + 0.05, "high": c + 0.3, "low": c - 0.3,
            "vol": 1000, "amount": 10000,
        })
    return out


BARS = _bars()
MMDS = [
    {"type": "1buy", "date": "2025-01-20", "confidence": 0.82, "anchor_val": 10.2,
     "bar_index": 46, "msg": "底背驰+趋势背驰确认"},
    {"type": "2buy", "date": "2025-03-10", "confidence": 0.71, "anchor_val": 11.0,
     "bar_index": 87, "msg": "回调不创新低"},
    {"type": "3buy", "date": "2025-04-15", "confidence": 0.66, "anchor_val": 12.1,
     "bar_index": 110, "msg": "突破中枢后回踩不破ZG"},
]
OUTCOMES = [
    {"type": "1buy", "date": "2025-01-20", "price": 10.2,
     "ret_5d": 4.61, "ret_10d": 7.09, "ret_20d": 13.17, "max_5d": 5.2, "min_5d": -0.3},
    {"type": "2buy", "date": "2025-03-10", "price": 11.0,
     "ret_5d": -0.95, "ret_10d": -0.27, "ret_20d": 0.96, "max_5d": 1.1, "min_5d": -1.8},
    {"type": "3buy", "date": "2025-04-15", "price": 12.1,
     "ret_5d": 1.41, "ret_10d": 2.72, "ret_20d": -0.30, "max_5d": 2.0, "min_5d": -0.9},
]

BASE = {
    "code": "SZ000333", "frequency": "daily", "category": "DAY",
    "bars": BARS, "bis": [], "xds": [], "zss": [], "mmds": MMDS,
    "fractals": [], "valid_fractals": [], "bcs": [], "boll": None,
    "macd": None, "levels": [], "zsds": [], "qsds": [],
    "candidates": [
        {"index": 46, "date": "2025-01-20", "kind": "fractal", "fx_type": "bottom",
         "signal": None},
    ],
}


def main() -> int:
    api = import_playwright()
    with api.sync_playwright() as pw:
        b = launch_pw(pw)
        pg = b.new_page(viewport={"width": 1600, "height": 1400})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))

        calls = {"train": 0, "review": 0}

        def _handler(route):
            u = route.request.url
            if "mode=review" in u:
                calls["review"] += 1
                body = {**BASE, "mmd_outcomes": OUTCOMES}
            else:
                calls["train"] += 1
                body = {**BASE, "mmd_outcomes": []}  # 闸门：训练模式不给
            route.fulfill(status=200, content_type="application/json",
                          body=json.dumps(body))

        pg.route("**/chanlun/train/session**", _handler)

        pg.goto(UI + "/learn?tab=train", wait_until="domcontentloaded", timeout=60000)
        pg.wait_for_timeout(5000)

        # 1) 开始训练（带闸门）
        for txt in ["开始训练", "开始"]:
            loc = pg.locator("button", has_text=txt).first
            if loc.count() and loc.is_visible():
                loc.click()
                break
        pg.wait_for_timeout(5000)

        # 2) 切到「复盘讲解」
        loc = pg.locator("button", has_text="复盘讲解").first
        if loc.count() and loc.is_visible():
            loc.click()
        pg.wait_for_timeout(6000)

        print("train 请求次数:", calls["train"], " review 请求次数:", calls["review"])
        print("页面错误:", errors[:3])

        panel = pg.locator(".review-panel")
        if panel.count() and panel.first.is_visible():
            rows = panel.first.locator("tbody tr").count()
            print("复盘表格行数:", rows)
            panel.first.screenshot(path="/tmp/f2_review.png")
            print("已截 .review-panel")
        else:
            pg.screenshot(path="/tmp/f2_review.png", full_page=True)
            print("未找到 .review-panel，改为整页截图")
        b.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
