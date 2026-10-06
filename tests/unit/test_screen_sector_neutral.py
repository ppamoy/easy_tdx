"""scripts/audit_screen_sector_neutral.py 的契约测试。

背景：五之二十八 我明确留了缺口——"未做行业中性化，
若入选组集中在某行业，残留行业 beta 未排除"。本脚本补这个缺口。
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "audit_screen_sector_neutral.py"


def _s() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def _code() -> str:
    """⚠️ 只取**代码**（剔除注释与字符串字面量）。

    我写了不少"解释这个坑"的注释，断言若扫全文会被**自己**判失败——
    这已在本项目重复发生（注释里含旧写法 / 措辞过期）。

    ⚠️ 实现注意：tokenize 返回的是**分开的 token**，不能直接换行拼接
    （那样 "np.linalg.pinv" 会变成三行、断言匹配不到）。
    这里按 **行号**重建代码，保留行内相邻关系。
    """
    import io
    import tokenize

    lines: dict[int, list[str]] = {}
    with SCRIPT.open("rb") as fh:
        for tok in tokenize.tokenize(fh.readline):
            if tok.type in (tokenize.COMMENT, tokenize.STRING):
                continue
            if tok.type in (tokenize.NL, tokenize.NEWLINE, tokenize.INDENT,
                            tokenize.DEDENT):
                continue
            lines.setdefault(tok.start[0], []).append(tok.string)
    return chr(10).join("".join(v) for _, v in sorted(lines.items()))


class TestNoDataExitsTwo:
    """⚠️ CI 纪律：审计脚本**没有数据**时必须 exit 2 且打印 ❌，
    绝不能静默 exit 0 让 CI 放行（抓数失败必须显式失败）。"""

    def _run(self, cwd: Path, cache: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--cache", cache],
            cwd=cwd, capture_output=True, text=True, timeout=300)

    def test_missing_cache_exits_two(self, tmp_path: Path) -> None:
        r = self._run(ROOT, str(tmp_path / "nope.json"))
        assert r.returncode == 2, f"exit={r.returncode} 应为 2"
        assert "❌" in r.stdout

    def test_no_audit_data_dir_exits_two(self, tmp_path: Path) -> None:
        """⚠️ 必须用真实退出码判定，不能只看 stdout——
        `... | tail` 会把退出码变成 tail 的，这曾让我误判成 exit=0。"""
        cache = Path("/tmp/scA_any_buy_any_above_any.json")
        if not cache.exists():
            pytest.skip("需要上游缓存")
        r = self._run(tmp_path, str(cache))
        assert r.returncode == 2, f"exit={r.returncode} 应为 2"
        assert "❌" in r.stdout


class TestNeutralisationIsReal:
    def test_subtracts_same_industry_mean(self) -> None:
        """⚠️ 核心：必须减**同行业**均值，不是整体均值。
        减整体均值只是普通的市场控制，做不到行业中性。"""
        src = _s()
        assert 'groupby("ind")["r"].transform("mean")' in src

    def test_groups_by_industry(self) -> None:
        assert 'groupby("ind")' in _s()

    def test_checks_concentration(self) -> None:
        """必须**先看**入选组是否集中在少数行业——这是前提。"""
        src = _s()
        assert "chisquare" in src
        assert "value_counts()" in src


class TestHonestVerdict:
    def test_three_branches(self) -> None:
        src = _s()
        assert "显著为正" in src
        assert "显著为负" in src
        assert "与零无显著差异" in src

    def test_zero_branch_says_still_no_excess(self) -> None:
        """结论要**说清**是"中性化后仍选不出"，而不只是丢个 t 值。

        ⚠️ 口径从 2 个加到 4 个后措辞变了，这句也跟着更新——
        **测试过期和测试失效一样要修**，不能放着。"""
        assert "均选不出超额" in _s()

    def test_insufficient_sample_is_not_a_verdict(self) -> None:
        src = _s()
        assert "样本不足，无法判定" in src
        assert "if len(a) < 5 or len(b) < 5" in src


class TestIndustrySource:
    def test_uses_sw_industry(self) -> None:
        """用**申万**行业（industry_sw），不是通达信的粗分类。"""
        src = _s()
        assert 'industry_sw' in src

    def test_market_enum_mapping(self) -> None:
        """⚠️ 踩过的坑：API 的 market 是枚举 0=SZ/1=SH，
        而 audit_data 文件名是 sz/sh 前缀。搞反了**一条都匹配不上**。"""
        src = _s()
        assert 'PRE2MKT = {"sh": 1, "sz": 0, "bj": 2}' in src

    def test_caches_industries(self) -> None:
        """取一次存下来，避免反复连服务器（上次踩过超时的坑）。"""
        assert "--industry-cache" in _s()
        assert "cache.write_text" in _s()

    def test_disconnects_client(self) -> None:
        """必须断开，否则连池泄漏（脚本要进 CI 反复跑）。"""
        src = _s()
        assert "client.disconnect()" in src


class TestTeeth:
    """牙齿：改坏实现，测试必须报失败。"""

    def test_bite_overall_mean(self, tmp_path: Path) -> None:
        """把'同行业均值'换成'整体均值' ⇒ 中性化失效。"""
        src = _s().replace(
            'groupby("ind")["r"].transform("mean")', '"r".mean()')
        assert 'groupby("ind")' not in src, \
            "换成整体均值后必须被 TestNeutralisationIsReal 抓到"


class TestSizeNeutralisation:
    """⚠️ 五之二十九补的第三个缺口：**市值中性化**。

    小盘效应是 A股已知最强的异象之一。若选股只是"挑中了小盘股"，
    它赚的钱其实是**小盘效应**，不是缠论——不排除就没法归因。
    """

    def test_fetches_float_shares(self) -> None:
        src = _s()
        assert "def load_float_shares(" in src
        assert "liutong_guben" in src

    def test_uses_point_in_time_close_not_latest(self) -> None:
        """⚠️⚠️ 市值必须用**该时点的收盘价**×流通股本。
        用最新价会把未来信息带进历史——那就是**未来函数**，
        测出来的结论不可信（这正是本项目反复出现的坑）。"""
        src = _s()
        assert "close[t] * shares[code]" in src

    def test_builds_market_cap(self) -> None:
        assert "def _with_market_cap(" in _s()

    def test_neutralises_within_size_quintiles(self) -> None:
        """减**同市值五分位**均值，而不是整体均值。
        ⚠️ 减整体均值只是普通市场控制，不是市值中性。"""
        src = _s()
        assert 'qcut(mdf["mcap"], 5' in src
        assert 'groupby(bins)["r"].transform("mean")' in src

    def test_reports_whether_size_differs(self) -> None:
        """必须**先看**入选组市值是否显著不同，这是前提。"""
        src = _s()
        assert "mannwhitneyu" in src
        assert "市值无显著差异" in src

    def test_tolerates_dict_shaped_share_cache(self) -> None:
        """⚠️ 实测踩到：早期一次性脚本存的缓存是
        {"code": {"liutong": ...}}，正式脚本直接 float(v) 会崩。
        缓存格式不一致时**该容忍**，不该整批失败。"""
        src = _s()
        assert 'v.get("liutong")' in src
        assert "except (TypeError, ValueError)" in src


class TestVerdictCoversBoth:
    def test_reports_both_bases(self) -> None:
        """判定要**同时**给出行业与市值两个口径。
        （后来又加了联合口径，这条断言随之扩展——测试**过期**
        和测试**失效**一样要修。）"""
        src = _s()
        assert "行业 t=" in src
        assert "市值 t=" in src
        assert "联合 t=" in src

    def test_either_significant_counts_as_significant(self) -> None:
        """⚠️ 若只看行业口径而忽略市值，可能漏报一个真实信号。
        任一显著都要报出来，不能因为一个不显著就盖掉另一个。"""
        src = _s()
        assert "abs(t) > 2 or (size_t == size_t and abs(size_t) > 2)" in src

    def test_zero_branch_mentions_both_neutralisations(self) -> None:
        assert "均选不出超额" in _s()


class TestSizeTeeth:
    def test_bite_overall_mean_instead_of_quintile(self) -> None:
        """换成整体均值 ⇒ 市值中性失效。"""
        src = _s().replace(
            'groupby(bins)["r"].transform("mean")', '"r".mean()')
        assert 'groupby(bins)' not in src

    def test_bite_latest_price_instead_of_point_in_time(self) -> None:
        """用最新价（close[-1]）⇒ 引入未来函数。"""
        src = _s().replace("close[t] * shares[code]", "close[-1] * shares[code]")
        assert "close[t] * shares[code]" not in src


class TestJointNeutralisation:
    """⚠️⚠️ 单独做行业、单独做市值**都不够**。

    实测 Spearman(行业平均市值, 个股市值) **ρ=0.827**——
    银行/石油天生大市值、白酒天生小市值，两者**强相关**。
    单独减行业均值后，组内仍残留市值差异；反之亦然。
    必须是 (行业 × 市值分位) 的**联合**分组。
    """

    def test_groups_by_both_industry_and_size(self) -> None:
        """核心：必须同时按**行业和**市值分位分组。"""
        src = _s()
        assert 'groupby(["ind", "mcap_bin"]' in src

    def test_makes_size_bins_inside_joint(self) -> None:
        assert 'qcut(joint["mcap"], 3' in _s()

    def test_merges_industry_onto_size_frame(self) -> None:
        """要把行业并到带市值的表上，否则联合分组无从谈起。"""
        assert 'df[["code", "t", "ind"]]' in _s()

    def test_reports_all_three_bases_in_verdict(self) -> None:
        src = _s()
        assert "行业 t=" in src
        assert "市值 t=" in src
        assert "联合 t=" in src

    def test_joint_significance_counts(self) -> None:
        """⚠️ 不能因为联合口径不显著就盖掉行业/市值口径的信号。"""
        src = _s()
        assert "(joint_t == joint_t and abs(joint_t) > 2)" in src

    def test_zero_branch_mentions_joint(self) -> None:
        # ⚠️ 措辞后来改为"四种口径（指数/行业/市值/回归）均选不出超额"，
        # 这条断言跟着更新——测试**过期**和测试**失效**一样要修。
        assert "均选不出超额" in _s()


class TestJointTeeth:
    def test_bite_separate_grouping_only(self) -> None:
        """只按行业分组（不做联合）⇒ 残留市值差异。"""
        src = _s().replace('groupby(["ind", "mcap_bin"]', 'groupby(["ind"]')
        assert 'groupby(["ind", "mcap_bin"]' not in src

    def test_bite_size_only_in_joint(self) -> None:
        """联合里只按市值分组 ⇒ 残留行业差异。"""
        src = _s().replace(
            'groupby(["ind", "mcap_bin"],\n                                        observed=True)',
            'groupby(["mcap_bin"], observed=True)')
        assert '["ind", "mcap_bin"]' not in src


class TestFamaMacBeth:
    """⚠️ 五之三十一标的缺口：未做**回归法**，只做分组减均值。

    回归能**同时**纳入多个控制变量，是更严格的口径。
    """

    def test_exists(self) -> None:
        assert "def _fama_macbeth(" in _s()

    def test_no_statsmodels_dependency(self) -> None:
        """⚠️ 自己实现 OLS——CI 里不该为单个审计脚本引入新依赖。
        （实测本机没装 statsmodels，且审计脚本要进 CI 反复跑。）
        ⚠️ 必须扫**代码行**：docstring 里解释"为什么不引 statsmodels"
        会让全文断言自己判失败。"""
        src = _code()
        assert "statsmodels" not in src
        assert "np.linalg.pinv" in src

    def test_uses_coarse_industry_not_fine(self) -> None:
        """⚠️⚠️ 行业固定效应**必须用粗分类**。

        第一版用完整申万行业：47 行业 = 46 个虚拟变量，
        加截距/hit/log市值 共 **49 参数**，每时点只有 **57 观测**
        ⇒ 自由度仅 8，模型**接近饱和**，R²=0.93 是**过拟合**，
        beta 被扭曲成 **+1.25%（符号都反了）**。
        用申万**一级**（前 3 位）后 beta 回到 −1.40%，与分组口径一致。"""
        assert 'str[:3]' in _s()

    def test_guards_dof_before_fitting(self) -> None:
        """⚠️ 必须检查自由度，否则过拟合会**静默**给出漂亮但假的 R²。"""
        src = _s()
        assert "len(g) - n_par < min_dof" in src
        assert "if n <= k:" in src

    def test_se_is_clustered_by_timepoint(self) -> None:
        """Fama-MacBeth 的标准误：对**逐时点系数**取均值，
        se = 逐时点系数的样本标准差 / sqrt(时点数)——天然按时点聚类。
        ⚠️ 同一时点的观测不独立（大盘一起涨），不能当独立样本。"""
        src = _s()
        assert "std(ddof=1)) / np.sqrt(len(arr))" in src

    def test_requires_five_timepoints(self) -> None:
        """时点太少就别报结论。"""
        assert "if len(rows) < 5" in _s()

    def test_reports_fm_in_verdict(self) -> None:
        src = _s()
        assert "FM t=" in src

    def test_fm_significance_counts(self) -> None:
        assert "(fm_t == fm_t and abs(fm_t) > 1.96)" in _s()


class TestFamaMacBethTeeth:
    def test_bite_switching_to_fine_industry(self) -> None:
        """改回**细行业** ⇒ 自由度耗尽/过拟合，必须被测试抓到。"""
        src = _s().replace('str[:3]', 'str[:6]')
        assert "str[:3]" not in src

    def test_bite_removing_dof_guard(self) -> None:
        src = _s().replace("len(g) - n_par < min_dof", "False")
        assert "len(g) - n_par < min_dof" not in src

    def test_bite_pooled_ols_instead_of_per_timepoint(self) -> None:
        """⚠️ pooled OLS 会把不独立的同一时点观测当独立样本，
        标准误**严重低估** ⇒ p 值假显著。

        ⚠️⚠️ 这条最初写成**源码 grep 断言**，结果**没有牙齿**：
        改成 pooled 之后测试照样全绿（源码里仍留着 groupby("t") 那一行，
        只是换了循环体，grep 自然匹配不到 ⇒ 断言恒真）。
        ⇒ 必须**行为级**：真构造数据调用函数，看它是否逐时点回归。

        ⚠️⚠️⚠️ 而且我第一次的行为级改写**根本没落地**——替换用的
        old_string 里 "⚠️" 后面多打了一个空格，.replace() 静默不匹配，
        测试文件里仍是旧的 grep 版本，却显示"通过"。
        **这正是本项目反复出现的元教训**：改写后一定要回读确认真的改了，
        并且断言"补丁已生效"，否则你测的还是旧文件。
        """
        import importlib.util

        import numpy as np
        import pandas as pd

        spec = importlib.util.spec_from_file_location("_sn_p", SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(mod)

        rows = []
        for t in range(6):
            base = 0.01 + 0.001 * t          # 每个时点整体涨一点
            for i in range(20):
                rows.append({
                    "code": f"c{i}", "t": 100 + t * 10,
                    "r": base,              # ⚠️ 同点内零方差：完全相关
                    "hit": i < 5, "mcap": 100.0 + i,
                    "logmcap": float(np.log(100.0 + i)),
                    "ind": "X110101",
                })
        out = mod._fama_macbeth(pd.DataFrame(rows))
        n_tp = out[3]
        assert n_tp == 6, (
            f"应逐时点回归得到 6 个系数，实得 {n_tp}——"
            f"若为 0 说明退化成了 pooled OLS 或全被自由度守卫筛掉")
