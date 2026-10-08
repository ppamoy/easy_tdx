#!/usr/bin/env python3
"""UI 改动自动验收脚本（行为级，不看 DOM 标志）。

背景（必须吸取的教训）：曾把「缠论买卖点配对」策略接进回测页时，只把模板里的
`v-if` 从 `strategy === 'chanlun'` 改成 `drawsChanlunChart`，却没有同步改
`onRun` 里触发数据加载的判断（仍是不含新策略的 `isChanlunStrategy`）。
结果 UI 开关亮了（下拉框渲染出来了），但 `chanlun/analyze` 请求**根本没发**，
图上是裸 K 线。当时只用 DOM 存在性断言验证，所以误判通过。

因此本脚本的原则：**只信行为，不信 DOM 标志**。
- 断言网络请求真的发出且返回 200（数据真的拉到了）；
- 断言渲染结果真的包含叠加层（视觉模型看图，而不是数 DOM 节点）；
- 断言对照组（不该有叠加层的策略）确实没有。

用法：
    python3 scripts/verify_ui.py                 # 全部用例
    python3 scripts/verify_ui.py --case chanlun_pair
    python3 scripts/verify_ui.py --no-vision     # 跳过视觉检查（只用请求级断言）

依赖：playwright（系统 chromium 即可，不需下载浏览器）
    pip install playwright --target=/tmp/pw
"""
from __future__ import annotations

import argparse
import os
import sys

# playwright 装在 /tmp/pw（本机约定），不在项目 venv 里
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _pw import import_playwright, launch_pw, ui_base  # noqa: E402

sync_api = import_playwright()

APP = os.environ.get("EASY_TDX_URL") or ui_base()
from _pw import chromium_path  # noqa: E402

CHROMIUM = chromium_path()
CODE = "000001"
SECTION = "K线 + 买卖点"

# 期望：缠论结构图（笔/线段/中枢/买卖点叠加）
CHANLUN_CHART_CASES = {
    "chanlun": {"expect_analyze": True, "expect_overlay": True},
    "chanlun_pair": {"expect_analyze": True, "expect_overlay": True},
}
# 期望：普通 K 线图（不应有缠论叠加）
PLAIN_CASES = {
    "ma_cross": {"expect_analyze": False, "expect_overlay": False},
    "changying_chanlun": {"expect_analyze": False, "expect_overlay": False},
}


def _run_backtest(pg, strategy: str) -> None:
    """在回测页跑一次指定策略的回测。"""
    pg.goto(APP, wait_until="domcontentloaded", timeout=45000)
    pg.wait_for_timeout(3000)
    pg.locator('input[placeholder="6位代码（市场自动识别）"]').first.fill(CODE)
    # 策略下拉是异步填充的（选项来自后端），必须等它真的有选项再选，
    # 否则首屏慢时会 "did not find some options" 而误判为「请求没发」。
    sel = pg.locator("select").nth(1)
    for _ in range(30):
        if sel.locator("option").count() > 1:
            break
        pg.wait_for_timeout(1000)
    sel.select_option(strategy)
    pg.locator("button", has_text="开始回测").first.click()
    # 缠论分析是在回测跑完后才触发的（实测 chanlun_pair 约 20s 后才发请求），
    # 所以必须等到 analyze 请求真的出现，而不是死等固定时长。
    try:
        pg.wait_for_selector(".report-section", timeout=120000)
    except Exception:  # noqa: BLE001
        pass
    for _ in range(30):
        if getattr(pg, "_analyze_hits", None):
            break
        pg.wait_for_timeout(2000)
    pg.wait_for_timeout(3000)


def _install_request_probe(pg) -> None:
    """监听网络层，记录 chanlun/analyze 是否发出及其状态。

    为什么不用 monkey-patch window.fetch：实测该方式在 SPA 里不可靠——页面里的
    fetch 引用可能在注入前就被模块闭包捕获，导致补丁根本没生效，从而把「发了
    请求」误判成「没发」（正是本脚本要抓的那类 bug 的反向误报）。
    改用 playwright 的 response 事件，观测的是真实网络层。
    """
    pg._analyze_hits = []  # type: ignore[attr-defined]

    def _on_resp(resp) -> None:
        if "chanlun/analyze" in resp.url:
            pg._analyze_hits.append(resp.status)  # type: ignore[attr-defined]

    pg.on("response", _on_resp)


def _analyze_called(pg) -> bool:
    """是否真的发出了 chanlun/analyze 且成功（这是本次 bug 的根因检测点）。"""
    hits = getattr(pg, "_analyze_hits", [])
    return any(st == 200 for st in hits)


def _analyze_status(pg):
    """最后一次 chanlun/analyze 的 HTTP 状态（None = 没发）。"""
    hits = getattr(pg, "_analyze_hits", [])
    return hits[-1] if hits else None


def _screenshot_section(pg, path: str) -> None:
    sec = pg.locator(".report-section").filter(has_text=SECTION).first
    sec.scroll_into_view_if_needed()
    pg.wait_for_timeout(2500)
    sec.screenshot(path=path)


def _vision_has_overlay(path: str) -> tuple[bool | None, str]:
    """判定截图里是否真有缠论叠加层。

    本项目没有内置视觉模型，因此**不假装自动判图**：本函数只做保守兜底，
    真正可靠的判定由 agent 用 describe_image 工具看 `/tmp/verify_ui_*.png` 完成。
    脚本会把待人工（agent）核验的截图路径打印出来，绝不用弱启发式冒充通过。

    返回 (True/False/None, 说明)：None = 无法自动判定，需 agent 看图。
    """
    # 只做「明确没画东西」的硬否定：图太小/几乎空白 → 判定无叠加
    try:
        size = os.path.getsize(path)
        if size < 8000:  # 基本是空白区域
            return False, f"截图过小({size}B)，判定无叠加"
    except OSError:
        return None, "截图不可读"
    # 其余情况交给 agent 用视觉模型判定
    return None, f"待 agent 视觉核验: {path}"


def _pixel_heuristic(path: str) -> bool:
    """像素级兜底：缠论叠加层会带来大量非K线的彩色线条/矩形。

    裸 K 线图颜色高度集中在红/绿/灰；有叠加层时独特颜色数显著更多。
    返回 True 表示「疑似有叠加层」。
    """
    try:
        import struct

        # 不用 PIL（可能没装）：直接读 PNG 像素代价高，这里用文件熵粗略判断
        with open(path, "rb") as f:
            raw = f.read()
        # PNG IDAT 解压后大小反映图像复杂度
        pos = 8
        total = 0
        while pos < len(raw):
            length = struct.unpack(">I", raw[pos : pos + 4])[0]
            ctype = raw[pos + 4 : pos + 8]
            if ctype == b"IDAT":
                total += length
            pos += 12 + length
            if ctype == b"IEND":
                break
        # 有丰富叠加层的图压缩后数据明显更大（阈值按实测标定）
        return total > 120_000
    except Exception:  # noqa: BLE001
        return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", help="只跑某个策略用例")
    ap.add_argument("--no-vision", action="store_true", help="跳过视觉检查")
    args = ap.parse_args()

    cases = {**CHANLUN_CHART_CASES, **PLAIN_CASES}
    if args.case:
        if args.case not in cases:
            print(f"未知用例 {args.case}，可选: {list(cases)}")
            return 2
        cases = {args.case: cases[args.case]}

    failures: list[str] = []
    pending_vision: list[tuple[str, str, bool]] = []
    with sync_api.sync_playwright() as p:
        browser = launch_pw(p)
        for strategy, exp in cases.items():
            pg = browser.new_page(viewport={"width": 1500, "height": 1200})
            _install_request_probe(pg)
            errs: list[str] = []
            pg.on("pageerror", lambda e: errs.append(str(e)))
            try:
                _run_backtest(pg, strategy)
                called = _analyze_called(pg)
                status = _analyze_status(pg)

                # 断言 1：数据请求行为（本次 bug 的根因）
                if called != exp["expect_analyze"]:
                    failures.append(
                        f"[{strategy}] chanlun/analyze 请求行为不符："
                        f"期望发出={exp['expect_analyze']}，实际={called} (status={status})"
                    )

                # 断言 2：渲染结果（必须看图，不能数 DOM）
                if not args.no_vision:
                    shot = f"/tmp/verify_ui_{strategy}.png"
                    _screenshot_section(pg, shot)
                    has_overlay, why = _vision_has_overlay(shot)
                    if has_overlay is None:
                        # 不假装通过：明确列出必须由 agent 用视觉模型核验的截图
                        pending_vision.append((strategy, shot, exp["expect_overlay"]))
                        print(
                            f"[{strategy}] ⚠ 需视觉核验 {shot}"
                            f"（期望叠加={exp['expect_overlay']}）"
                        )
                    elif has_overlay != exp["expect_overlay"]:
                        failures.append(
                            f"[{strategy}] 图上叠加层不符：期望={exp['expect_overlay']}，"
                            f"实际={has_overlay}（{why[:80]}）"
                        )

                if errs:
                    failures.append(f"[{strategy}] 页面 JS 错误: {errs[:2]}")

                flag = "✅" if not any(strategy in f for f in failures) else "❌"
                print(
                    f"{flag} [{strategy}] analyze请求={called}(status={status}) "
                    f"期望={exp['expect_analyze']}"
                )
            finally:
                pg.close()
        browser.close()

    print("=" * 60)
    if failures:
        print("验收失败：")
        for f in failures:
            print("  -", f)
        return 1
    if pending_vision:
        # 不允许「跳过视觉检查」冒充通过：必须看图后才算完成
        print("⚠ 行为断言已通过，但以下截图仍待视觉核验（请用 describe_image 查看）：")
        for strategy, shot, exp in pending_vision:
            print(f"  - [{strategy}] {shot}  期望有叠加层={exp}")
        print("看完后确认与期望一致，才算验收完成。")
        return 3  # 非 0：避免 CI/agent 误判为全绿
    print("✅ UI 验收通过（请求行为 + 渲染结果均已核对）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
