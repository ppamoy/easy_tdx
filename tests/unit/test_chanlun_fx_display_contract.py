"""分型展示契约测试：展示层必须能拿到 valid_fractals，不得渲染原始分型。

背景（已发生过的回归）：原始 ``fractals`` 是 find_fractals 逐三根滑动窗口的
产物，含大量**共用K线**的相邻分型（如「底-顶-底」挤在连续三根K线上）。这类
分型不符合缠论原文「相邻分型至少隔 1 根独立K线」的要求，直接渲染会画出伪分型。

因此约定两条契约，本文件静态锁死它们（真正的渲染正确性另由
scripts/verify_fx_pages.py 在浏览器里验证）：

  1. 前端：凡渲染 ChanlunChart 的页面，都必须传 ``:validFxs``。
  2. 后端：凡往响应里塞 ``fractals`` 的路由，都必须同时给 ``valid_fractals``。

为什么用静态检查而不是跑服务：这两条是「接线」约定，静态检查能在 CI 里零成本
跑（无需后端/浏览器），且能精准指出漏了哪个文件。
"""

from __future__ import annotations

import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
VIEWS_DIR = os.path.join(ROOT, "web-ui", "src", "views")
ROUTERS_DIR = os.path.join(ROOT, "src", "easy_tdx", "web", "routers")


def _vue_files() -> list[str]:
    if not os.path.isdir(VIEWS_DIR):
        pytest.skip(f"前端目录不存在: {VIEWS_DIR}")
    return [f for f in sorted(os.listdir(VIEWS_DIR)) if f.endswith(".vue")]


def _router_files() -> list[str]:
    if not os.path.isdir(ROUTERS_DIR):
        pytest.skip(f"后端目录不存在: {ROUTERS_DIR}")
    return [f for f in sorted(os.listdir(ROUTERS_DIR)) if f.endswith(".py")]


def test_every_chanlun_chart_passes_valid_fxs() -> None:
    """契约 1：所有用 ChanlunChart 的页面都必须传 :validFxs。"""
    offenders: list[str] = []
    checked = 0
    for fn in _vue_files():
        src = open(os.path.join(VIEWS_DIR, fn), encoding="utf-8").read()
        if "ChanlunChart" not in src:
            continue
        n_fxs = len(re.findall(r":fxs\s*=", src))
        if not n_fxs:
            continue
        checked += 1
        n_valid = len(re.findall(r":validFxs\s*=", src))
        if n_valid < n_fxs:
            offenders.append(f"{fn}: :fxs×{n_fxs} 但 :validFxs×{n_valid}")

    assert not offenders, (
        "以下页面渲染缠论图却没传 :validFxs，会渲染含重叠的原始分型：\n  " + "\n  ".join(offenders)
    )
    assert checked > 0, "没找到任何渲染 ChanlunChart 的页面，检查逻辑可能失效"


def test_every_router_offers_valid_fractals() -> None:
    """契约 2：给 fractals 的后端路由必须同时给 valid_fractals。"""
    offenders: list[str] = []
    for fn in _router_files():
        src = open(os.path.join(ROUTERS_DIR, fn), encoding="utf-8").read()
        n_set = len(re.findall(r'["\']fractals["\']\s*\]?\s*=', src))
        if not n_set:
            continue
        n_valid = len(re.findall(r'["\']valid_fractals["\']\s*\]?\s*=', src))
        if n_valid < n_set:
            offenders.append(f"{fn}: fractals×{n_set} 但 valid_fractals×{n_valid}")

    assert not offenders, "以下路由只返回原始 fractals，前端拿不到干净数据源：\n  " + "\n  ".join(
        offenders
    )


def test_chanlun_chart_falls_back_only_when_omitted() -> None:
    """图表组件只在 validFxs「完全没传」时才回退，空数组不得回退。

    这是之前踩过的坑：旧实现写成 ``validFxs && validFxs.length ? validFxs : fxs``，
    一旦调用方传了空数组（后端还没给该字段时很常见），就静默回退到脏数据。
    """
    comp = os.path.join(ROOT, "web-ui", "src", "components", "ChanlunChart.vue")
    if not os.path.isfile(comp):
        pytest.skip("ChanlunChart.vue 不存在")
    src = open(comp, encoding="utf-8").read()

    assert "props.validFxs ?? props.fxs" in src or re.search(
        r"props\.validFxs\s*\?\?\s*props\.fxs", src
    ), "应使用 `validFxs ?? fxs`（仅在 undefined 时回退），而非按 length 判断"
    # 不得再出现「按长度判断」的旧写法
    assert not re.search(r"validFxs\.length\s*\?", src), (
        "不应按 validFxs.length 判断是否回退——空数组会静默回退到脏的 fxs"
    )
