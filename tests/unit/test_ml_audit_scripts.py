"""多级别审计脚本的回归测试。

覆盖一个**踩过且代价很高**的坑：60min 版矩阵脚本第一跑的结果与 30min 版
**逐位相同**，因为脚本里 `CACHE` 被硬编码成 `audit_cache`（30min 的信号缓存），
而次级别数据已经换成 60min —— **数据换了、信号没换**，结果静默错误。

本测试从**源码层面**断言两个变体的缓存目录不同源，防止改回去。

另外断言：
- `_ml_precompute60.load_pair` 真的读 60min 文件（不是 30min）
- 两个 precompute 模块的 `CACHE` 必须不同目录
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"


def _load(name: str, path: Path):
    """按文件路径导入脚本模块（scripts/ 不在包内，不能直接 import）。"""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def m30():
    return _load("_t_ml_precompute", SCRIPTS / "_ml_precompute.py")


@pytest.fixture(scope="module")
def m60():
    p = SCRIPTS / "_ml_precompute60.py"
    if not p.exists():
        pytest.skip("_ml_precompute60.py 不存在")
    return _load("_t_ml_precompute60", p)


def test_precompute60_cache_dir_differs(m30, m60):
    """两个变体的缓存目录必须不同 —— 否则会互相覆盖/串读。"""
    assert m30.CACHE != m60.CACHE, (
        f"两个 precompute 的 CACHE 相同（{m30.CACHE}）⇒ "
        f"30min 与 60min 的信号会串读"
    )
    assert m60.CACHE.name == "audit_cache60"


def test_precompute60_reads_60min_files(m60):
    """_ml_precompute60 必须读 *_60min.json，不是 *_30min.json。"""
    src = (SCRIPTS / "_ml_precompute60.py").read_text()
    assert "_60min.json" in src
    # 除注释外不应再引用 30min 的数据文件
    data_lines = [
        ln for ln in src.splitlines()
        if "30min.json" in ln and not ln.strip().startswith("#")
    ]
    assert not data_lines, f"_ml_precompute60 仍引用 30min 数据文件：{data_lines}"


def test_matrix60_imports_cache_not_hardcode():
    """60min 矩阵脚本的 CACHE 必须从 precompute 模块导入，不能自己硬编码。

    曾硬编码 `CACHE = ROOT / "audit_cache"` ⇒ 与 30min 结果逐位相同。
    """
    p = SCRIPTS / "audit_chanlun_full_theory60.py"
    if not p.exists():
        pytest.skip("脚本不存在")
    src = p.read_text()
    bad = [ln for ln in src.splitlines() if ln.strip().startswith("CACHE = ROOT")]
    assert not bad, (
        f"60min 脚本硬编码了 CACHE（{bad}）⇒ 次级别换成 60min 后信号仍读 30min 缓存，"
        f"结果会静默沿用旧值。请改为 `from _ml_precompute60 import CACHE`"
    )
    assert "from _ml_precompute60 import CACHE" in src


def test_matrix30_cache_matches_its_own_precompute(m30):
    """30min 矩阵脚本的 CACHE 必须等于 _ml_precompute 的 CACHE。"""
    p = SCRIPTS / "audit_chanlun_full_theory.py"
    if not p.exists():
        pytest.skip("脚本不存在")
    src = p.read_text()
    assert f'ROOT / "{m30.CACHE.name}"' in src, (
        f"audit_chanlun_full_theory.py 的 CACHE 与 _ml_precompute 的 "
        f"({m30.CACHE.name}) 不一致"
    )


def test_matrix60_has_cache_guard():
    """60min 矩阵脚本必须带「缓存目录 vs 次级别 bar 数」的守门断言。"""
    p = SCRIPTS / "audit_chanlun_full_theory60.py"
    if not p.exists():
        pytest.skip("脚本不存在")
    src = p.read_text()
    assert "守门" in src, (
        "60min 矩阵脚本缺少守门断言；没有它，'缓存与周期不匹配'会静默发生"
    )
    assert "audit_cache60" in src
