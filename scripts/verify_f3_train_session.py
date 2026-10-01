#!/usr/bin/env python3
"""渲染验证 F3 训练数据：历史区间回放 + 会话保存/续练（V731）。

需求 F3 两条此前**都没实现**：训练页无日期输入、请求不传 start_date/end_date；
全项目 localStorage 也没有训练会话持久化的影子。本脚本起真实前后端，用
Playwright 拦截 session 接口，截图确认：
  1) 配置栏真的渲染出「历史区间起/止」日期输入；
  2) 点击「保存进度」后，「继续上次训练」按钮真的出现（续练入口可用）；
  3) 刷新页面后存档仍在（真的持久化了，不是内存态）；
  4) 【安全】localStorage 存档里不含答案/未来走势。

按 AGENTS.md 纪律：渲染类验证必须**真看渲染结果**（截图 + 图像模型），
不能只断言 DOM 存在或请求 200。

用法（需先起后端 8000 + 前端 3012）：
    python3 scripts/verify_f3_train_session.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _pw import chromium_path, import_playwright  # noqa: E402

UI = os.environ.get("EASY_TDX_UI", "http://127.0.0.1:3012")
SESSION_KEY = "easy_tdx_train_session_v1"


def _bars(n: int = 160) -> list[dict]:
    return [
        {
            "datetime": f"2025-{(1 + i // 28) % 12 + 1:02d}-{(i % 28) + 1:02d}T15:00:00",
            "open": 10.0, "close": 10.0 + i * 0.01,
            "high": 10.3, "low": 9.7, "vol": 1000, "amount": 10000,
        }
        for i in range(n)
    ]


PAYLOAD = {
    "code": "SZ000333", "frequency": "daily", "category": "DAY",
    "bars": _bars(), "bis": [], "xds": [], "zss": [], "mmds": [],
    "fractals": [], "valid_fractals": [], "bcs": [], "boll": None,
    "macd": None, "levels": [], "zsds": [], "qsds": [],
    # 带答案的候选点 —— 用来验证存档里**不会**出现 1buy
    "candidates": [
        {"index": 46, "date": "2025-01-20", "kind": "mmd",
         "signal": {"type": "1buy", "confidence": 0.82}},
    ],
    "mmd_outcomes": [{"type": "1buy", "date": "2025-01-20", "ret_20d": 13.17}],
}


def main() -> int:
    api = import_playwright()
    with api.sync_playwright() as pw:
        b = pw.chromium.launch(
            headless=True, executable_path=chromium_path(), args=["--no-sandbox"]
        )
        pg = b.new_page(viewport={"width": 1700, "height": 1200})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))

        pg.route(
            "**/chanlun/train/session**",
            lambda r: r.fulfill(status=200, content_type="application/json",
                                body=json.dumps(PAYLOAD)),
        )

        pg.goto(UI + "/learn?tab=train", wait_until="domcontentloaded", timeout=60000)
        pg.wait_for_timeout(5000)

        # 1) 配置栏截图（看日期控件 + 保存按钮）
        bar = pg.locator(".config-bar")
        if bar.count() and bar.first.is_visible():
            bar.first.screenshot(path="/tmp/f3_config.png")
            print("已截 .config-bar")
        else:
            pg.screenshot(path="/tmp/f3_config.png", full_page=True)
            print("未找到 .config-bar → 整页截图")

        n_date = pg.locator('.config-bar input[type="date"]').count()
        print("配置栏日期输入控件数量:", n_date)

        # 2) 点「保存进度」
        save_btn = pg.locator("button", has_text="保存进度").first
        has_save = save_btn.count() and save_btn.is_visible()
        print("「保存进度」按钮可见:", has_save)
        if has_save:
            save_btn.click()
            pg.wait_for_timeout(2000)

        saved = pg.evaluate(f"() => localStorage.getItem({SESSION_KEY!r})")
        print("存档是否写入:", bool(saved))
        if saved:
            print("存档内容:", saved[:220])
            print("存档含 '1buy'(答案)?", "1buy" in saved)
            print("存档含 '13.17'(未来走势)?", "13.17" in saved)

        # 3) 刷新页面 → 存档应仍在，「继续上次训练」应出现
        pg.reload(wait_until="domcontentloaded")
        pg.wait_for_timeout(5000)
        resume_btn = pg.locator("button", has_text="继续上次训练").first
        print("刷新后「继续上次训练」可见:", resume_btn.count() and resume_btn.is_visible())
        print("页面错误:", errors[:3])

        if bar.count() and bar.first.is_visible():
            bar.first.screenshot(path="/tmp/f3_resume.png")
            print("已截刷新后的 .config-bar")
        b.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
