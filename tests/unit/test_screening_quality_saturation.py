"""V733 五之二十六：质量分封顶缺陷的回归测试。

⚠️ 这组测试的价值全在"牙齿"上——**如果它们没有牙齿，就是又一轮自我安慰**。
每一项都标明了对应的坏版本。
"""
from pathlib import Path

SRC = (Path(__file__).resolve().parents[2] /
       "src" / "easy_tdx" / "web" / "routers" / "screening.py")


def _s() -> str:
    return SRC.read_text(encoding="utf-8")


def _quality_fn() -> str:
    """只截 `_calc_stock_quality` 函数体。

    ⚠️ 教训：文件里**别处**（长赢筛选 `_pass_screening`）也有
    `elif bi_count >= 10 and zs_count >= 3` 这样的阶梯判定，
    我第一版按全文 grep 断言"没有阶梯" ⇒ **假失败**。
    改坏的东西和被测的东西必须分清。"""
    s = _s()
    i = s.index("def _calc_stock_quality(")
    j = s.index(chr(10) + "def ", i + 10)
    return s[i:j]


class TestNoStaircase:
    def test_staircase_thresholds_removed(self) -> None:
        """⚠️ 原实现是阶梯式：bi>=20 加 15、bi>=10 加 10……
        500 根 K 线（笔 100+）下**全部顶格**。
        牙齿：把阶梯加回来 ⇒ 本测试必须红。"""
        s = _quality_fn()
        assert "elif bi_count >=" not in s
        assert "elif zs_count >=" not in s
        assert "elif mmd_count >=" not in s

    def test_uses_continuous_log(self) -> None:
        assert "_log1p(" in _quality_fn()


class TestSaturationFixed:
    def test_coefficients_are_data_derived(self) -> None:
        """⚠️ 我第一版"修复"随手写了 5.0/7.0/5.0/2.5，
        结果 log1p(117)*5 = 24 远超上限 15 ⇒ **照样全顶格**，
        修了跟没修一样（实测满分率 95%→95%）。
        现在的系数必须注明是**从实测分布反推**的。"""
        s = _quality_fn()
        assert "从实测分布反推" in s
        assert "中位=117" in s

    def test_coefficients_match_measured_distribution(self) -> None:
        """锁死这四个系数：它们是按"中位数落在上限 60%"算出来的。
        若有人改回 5.0/7.0/5.0/2.5，这里必须红。
        ⚠️ 牙齿实测：改回旧系数后本测试**确实报失败**。"""
        s = _quality_fn()
        for coef in ("1.9 * _log1p(bi_count)",
                     "3.1 * _log1p(zs_count)",
                     "1.6 * _log1p(mmd_count)",
                     "1.0 * _log1p(bc_count)"):
            assert coef in s, f"缺少数据反推的系数：{coef}"

    def test_caps_still_present(self) -> None:
        """必须仍有上限 —— 无上限的话结构多的股票会无限加分。"""
        s = _quality_fn()
        for cap in ("min(15.0,", "min(10.0,", "min(5.0,"):
            assert cap in s

    def test_log1p_is_safe(self) -> None:
        """_log1p 不能对负数/None 抛异常（结构数理论上非负，但要防脏数据）。"""
        s = _s()
        assert "def _log1p(" in s
        assert "max(0, int(x))" in s
        assert "except (TypeError, ValueError)" in s


class TestHonestAboutPredictivePower:
    """⚠️⚠️ 最关键的一组：**别把"修了缺陷"说成"功能有效了"。**

    实测：修复后 ρ=−0.04、p=0.66，质量分**仍然排不出**未来表现。
    所以文档/注释里必须写清这一点，否则就是误导用户。"""

    def test_docstring_admits_no_predictive_power(self) -> None:
        s = _quality_fn()
        assert "不代表改完就能选股赚钱" in s

    def test_docstring_points_to_the_negative_audit(self) -> None:
        s = _quality_fn()
        assert "五之二十五" in s

    def test_does_not_reweight_underlying_criteria(self) -> None:
        """刻意**不**改"买卖点结构密度"这个底层口径——
        重新标定权重是更大的改动，必须重做前瞻验证才能下结论。"""
        s = _quality_fn()
        assert "不改动" in s or "不改变" in s


class TestTopNStillSortsByScore:
    def test_sorting_uses_quality_score(self) -> None:
        """top_n 仍然按质量分排序（这正是本节要修的"排序形同虚设"）。"""
        s = _s()
        assert 'sort(key=lambda x: x.get("quality_score", 0), reverse=True)' in s

    def test_score_is_used_for_topn_cut(self) -> None:
        s = _s()
        assert r'results["qualified"] = results["qualified"][:top_n]' in s
