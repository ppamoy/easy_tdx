"""V731：区间套（qujiantao）的「合成数据」来源标注契约。

背景（实测确认）：
- :mod:`easy_tdx.chanlun.level_synth` 自述「这只是**近似**，不是真实 Tick……
  不能当成精确的小级别买卖点」；
- :func:`compute_qujiantao_cross_period` 的契约要求「另一份**真实行情**」；
- 但 ``chanlun_pair._attach_cross_period_qujiantao`` 拿不到真实低级别数据，
  实际喂进去的是 level_synth **合成**的 K 线，且该方法 docstring 此前自称
  打「**真**跨周期区间套」标签。

三者互相矛盾：一个自称"真"的标签建立在自称"近似"的数据上，而它被
``require_qujiantao`` 用来过滤**真实交易**。

修复口径：新增 ``synthetic`` 参数，调用方必须显式声明来源；结果里带
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


class TestCallerDeclaresSynthetic:
    """chanlun_pair 用合成数据喂养，必须声明 synthetic=True。

    这条是**反向锁定**：若将来有人删掉调用处的 synthetic=True（或改回
    不声明），本测试失败 —— 防止"真区间套"标签重新建立在合成数据上却
    不告知调用方。
    """

    def test_chanlun_pair_passes_synthetic_true(self) -> None:
        import easy_tdx.backtest.strategies.chanlun_pair as cp

        # 该方法定义在 ChanlunPairStrategy 上（不是模块级函数）。
        #
        # 用 **AST** 检查真实的调用关键字参数，而不是全文搜 "synthetic=True"
        # —— 后者会被 docstring 里出现的同样字样骗过（实测：删掉调用处的
        # 实参后，全文匹配仍命中注释 ⇒ 测试假通过）。结构化断言才可靠。
        fn = cp.ChanlunPairStrategy._attach_cross_period_qujiantao
        src = inspect.getsource(fn)
        assert "synthesize_lower_level" in src, (
            "该方法仍在用合成数据；若已改为真实行情，请同步更新本测试口径"
        )

        import ast
        import textwrap

        tree = ast.parse(textwrap.dedent(src))
        found: list[bool] = []
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "compute_qujiantao_cross_period"
            ):
                kws = {k.arg for k in node.keywords}
                found.append("synthetic" in kws)
        assert found, "未找到 compute_qujiantao_cross_period 调用点"
        assert all(found), (
            "用 level_synth 合成数据喂养 compute_qujiantao_cross_period 时，"
            "必须显式传 synthetic=... 声明来源，否则 nested 会被误当作"
            "原文意义的真区间套（用于 require_qujiantao 过滤真实交易）"
        )

    def test_level_synth_disclaims_precision(self) -> None:
        """level_synth 自述"近似"——据此确认"真区间套"表述不成立。"""
        import easy_tdx.chanlun.level_synth as ls

        doc = ls.__doc__ or ""
        assert "近似" in doc
        assert "真实 Tick" in doc or "不能当成精确" in doc
