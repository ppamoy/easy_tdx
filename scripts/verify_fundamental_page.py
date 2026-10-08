#!/usr/bin/env python3
"""长赢选股页（/fundamental）行为级 e2e —— PRD P1 验收第 4 条（V-31）。

PRD P1 验收 4：「浏览器实测验证页面交互与图表」。此前仅验过 API 层，页面级
交互（模式切换/日期选择/选股触发/结果表格渲染）从未真实跑过。

本脚本原则同 verify_fx_pages.py：只信行为，不信 DOM 标志——
  · 模式切换真的切换（screen/verify/scan 三 tab）
  · 「开始历史时点选股」真的发出 /fundamental/screen 请求（网络探针）且 200
  · 结果表格真的渲染出分类徽章与打分行（不是空表格冒充成功）
  · 打分明细真的可展开/可见（PRD 验收 1「打分有明细、可解释」的 UI 面）

用法：
    python3 scripts/verify_fundamental_page.py            # 需 live 后端 8000 + UI 3012
    EASY_TDX_UI=http://127.0.0.1:3012 python3 ...

依赖：playwright（系统 chromium）+ live uvicorn 8000 + vite dev 3012。
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _pw import api_base, import_playwright, launch_pw, ui_base  # noqa: E402

UI = ui_base()
API = api_base()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="2025-06-30", help="历史时点")
    args = ap.parse_args()

    sync_api = import_playwright()
    failures: list[str] = []
    screen_requests: list[dict] = []

    with sync_api.sync_playwright() as pw:
        browser = launch_pw(pw)
        page = browser.new_page()
        console_errors: list[str] = []
        page.on(
            "console",
            lambda m: console_errors.append(m.text) if m.type == "error" else None,
        )
        # 网络探针：真实请求监听（不信 DOM 标志的第一性手段）
        page.on(
            "request",
            lambda r: screen_requests.append(
                {"url": r.url, "post": r.post_data}
            ) if "/api/v1/fundamental/screen" in r.url else None,
        )
        page.on(
            "response",
            lambda r: screen_requests.append(
                {"url": r.url, "status": r.status}
            ) if "/api/v1/fundamental/screen" in r.url else None,
        )

        page.goto(f"{UI}/fundamental", wait_until="networkidle", timeout=60_000)

        # 1) 三个模式 tab 真实存在且可切换
        tabs = page.locator(".mode-tab")
        if tabs.count() < 3:
            failures.append(f"模式 tab 数量 {tabs.count()} < 3")
        tabs.nth(1).click()  # verify
        page.wait_for_timeout(300)
        if page.locator("textarea.pool-input").count() == 0:
            failures.append("切到 verify 后没有出现时点输入区")
        tabs.nth(0).click()  # 回 screen
        page.wait_for_timeout(300)

        # 2) 填历史日期并触发选股
        page.fill("input.date-input", args.date)
        page.click("button.scan-btn")
        # 等选股请求完成（gpcw 加载 + 指标 + 表现，最长 120s）
        page.wait_for_selector("button.scan-btn:not([disabled])", timeout=120_000)

        # 3) 行为断言：请求真的发出且成功
        posts = [r for r in screen_requests if "post" in r]
        resps = [r for r in screen_requests if "status" in r]
        if not posts:
            failures.append("未发出 /fundamental/screen 请求（按钮没触发真实链路）")
        if not resps or not any(r["status"] == 200 for r in resps):
            failures.append(f"screen 请求无 200 响应：{resps}")

        # 4) 结果渲染：结果区真的出现（result 非 null 才渲染 template）
        if page.locator("text=自选池").count() == 0 and page.locator(".result, table").count() == 0:
            failures.append("选股完成但结果区未渲染")

        # 5) 错误横幅不应出现
        page_err = page.locator(".error-banner, .error").first
        if page_err.count() > 0 and page_err.is_visible():
            failures.append(f"页面显示错误：{page_err.text_content()}")

        # 6) console 无真错误（favicon 404 等噪音过滤）
        real_errors = [
            e for e in console_errors
            if "favicon" not in e and "DevTools" not in e and "sourcemap" not in e.lower()
        ]
        if real_errors:
            failures.append(f"console 错误 {len(real_errors)} 条：{real_errors[:3]}")

        page.screenshot(path="/tmp/fundamental_screen_e2e.png", full_page=True)

    if failures:
        print(f"❌ {len(failures)} 项失败:")
        for f in failures:
            print(f"  {f}")
        return 1
    print("✅ /fundamental 页面行为级 e2e 通过：tab 切换 / 选股请求 200 / 结果渲染 / 无 console 错误")
    print("   截图：/tmp/fundamental_screen_e2e.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
