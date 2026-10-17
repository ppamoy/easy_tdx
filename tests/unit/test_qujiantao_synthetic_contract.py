"""V731：区间套（qujiantao）的「合成数据」来源标注契约。

背景（实测确认）：
- :mod:`easy_tdx.chanlun.level_synth` 自述「这只是**近似**，不是真实 Tick……
  不能当成精确的小级别买卖点」；
- :func:`compute_qujiantao_cross_period` 的契约要求「另一份**真实行情**」。

曾经的矛盾：已废弃删除的 ``chanlun_pair._attach_cross_period_qujiantao``
拿不到真实低级别数据，实际喂进去的是 level_synth **合成**的 K 线，而它
自称打「**真**跨周期区间套」标签，且被 ``require_qujiantao`` 用来过滤
**真实交易** —— 一个自称"真"的标签建立在自称"近似"的数据上。
（该策略因「伪区间套不符合原文」被整体移除；真区间套将放前端页面用
真实双周期数据实现。）

修复口径保留：新增 ``synthetic`` 参数，调用方必须显式声明来源；结果里带
``synthetic`` 字段供调用方/前端区分。本测试锁定该契约不被悄悄绕过。
"""

from __future__ import annotations

import inspect

from easy_tdx.chanlun.qujiantao import compute_qujiantao_cross_period


def _mk_mmd_with_bi(buy: bool = True):
    """构造一个带锚定笔的 MMD（足以走到主循环，而非早期 return）。"""
    from datetime import datetime

    from easy_tdx.chanlun.types import BI, FX, MMD, FXType, MMDType

    def _fx(index: int, is_top: bool):
        return FX(
            fx_type=FXType.DING if is_top else FXType.DI,
            k=type(
                "CLK", (), {"k_index": index * 10, "index": index, "date": datetime(2025, 1, 1)}
            )(),
            klines=[],
            val=10.0 + index,
            index=index,
            done=True,
        )

    # Line 无 done 字段（完成与否看 end.done），见 types.py
    bi = BI(start=_fx(0, False), end=_fx(10, True), direction="up", high=12.0, low=10.0)
    bi.start.bar_index = 0
    bi.end.bar_index = 10
    mmd = MMD(
        mmd_type=MMDType.BUY_3 if buy else MMDType.SELL_3,
        msg="",
        confidence=0.5,
    )
    mmd.bi = bi
    return mmd


class TestSyntheticContract:
    """synthetic 参数必须存在并如实传播到结果里。"""

    def test_signature_accepts_synthetic(self) -> None:
        sig = inspect.signature(compute_qujiantao_cross_period)
        assert "synthetic" in sig.parameters
        # 默认 False：既有调用方行为不变
        assert sig.parameters["synthetic"].default is False

    def test_synthetic_true_is_propagated(self) -> None:
        mmd = _mk_mmd_with_bi()
        # 给一份非空低级别容器，确保走到主循环而非早期 return
        low_bi = _mk_mmd_with_bi().bi
        res = compute_qujiantao_cross_period([mmd], bis_low=[low_bi], synthetic=True)
        assert len(res) == 1
        r = res[0]
        assert isinstance(r, dict)
        # 走到主循环才会有 method=cross_period；早期 return 是 'none'
        assert r["method"] == "cross_period", f"未走到主循环：{r}"
        assert r["synthetic"] is True

    def test_synthetic_defaults_false(self) -> None:
        """对照组：不声明时必须是 False（真实行情路径不受影响）。"""
        mmd = _mk_mmd_with_bi()
        low_bi = _mk_mmd_with_bi().bi
        res = compute_qujiantao_cross_period([mmd], bis_low=[low_bi])
        r = res[0]
        assert isinstance(r, dict)
        assert r["method"] == "cross_period", f"未走到主循环：{r}"
        assert r["synthetic"] is False


class TestNoSyntheticDataCaller:
    """仓库里不得再存在「用合成数据喂 compute_qujiantao_cross_period」的调用方。

    这条是**反向锁定**：曾经的 chanlun_pair 就是这么干的（喂 level_synth
    合成 K 线却自称真区间套），已因「伪区间套不符合原文」整体移除。
    本测试防止同样的坑复发 —— 若将来有人再写一个策略用
    ``synthesize_lower_level`` 的产物去喂跨周期区间套，必须显式传
    ``synthetic=...`` 声明来源，否则本测试失败。

    判定用 **AST** 结构化扫描（不是全文搜 "synthetic=True"）—— 后者会被
    docstring 里出现的同样字样骗过（实测：删掉调用处的实参后，全文匹配
    仍命中注释 ⇒ 测试假通过）。
    """

    def _scan_pkg(self, pkg: str) -> list[str]:
        import ast
        from pathlib import Path

        import easy_tdx

        root = Path(easy_tdx.__file__).resolve().parent
        bad: list[str] = []
        for f in sorted(root.rglob("*.py")):
            if "__pycache__" in f.parts:
                continue
            try:
                tree = ast.parse(f.read_text(encoding="utf-8"))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "compute_qujiantao_cross_period"
                ):
                    kws = {k.arg for k in node.keywords}
                    if "synthetic" not in kws:
                        bad.append(f"{f.relative_to(root)}:{node.lineno}")
        return bad

    def test_no_caller_feeds_synthetic_without_declaring(self) -> None:
        """src/ 下所有调用点都必须显式声明 synthetic。"""
        bad = self._scan_pkg("easy_tdx")
        assert not bad, (
            "以下调用点用数据喂 compute_qujiantao_cross_period 却没声明 "
            f"synthetic=... ⇒ nested 可能被误当作原文意义的真区间套：{bad}"
        )

    def test_chanlun_pair_module_gone(self) -> None:
        """chanlun_pair 已废弃删除（伪区间套策略，不再进注册表）。"""
        import importlib.util

        assert importlib.util.find_spec("easy_tdx.backtest.strategies.chanlun_pair") is None, (
            "chanlun_pair 模块仍存在 —— 它用 level_synth 合成数据做伪区间套，"
            "已废弃删除，请勿复活"
        )

    def test_level_synth_disclaims_precision(self) -> None:
        """level_synth 自述"近似"——据此确认"真区间套"表述不成立。"""
        import easy_tdx.chanlun.level_synth as ls

        doc = ls.__doc__ or ""
        assert "近似" in doc
        assert "真实 Tick" in doc or "不能当成精确" in doc
