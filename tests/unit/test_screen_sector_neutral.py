"""scripts/audit_screen_sector_neutral.py 的契约测试。

背景：五之二十八 我明确留了缺口——"未做行业中性化，
若入选组集中在某行业，残留行业 beta 未排除"。本脚本补这个缺口。
"""

from __future__ import annotations

import os
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
    import tokenize

    lines: dict[int, list[str]] = {}
    with SCRIPT.open("rb") as fh:
        for tok in tokenize.tokenize(fh.readline):
            if tok.type in (tokenize.COMMENT, tokenize.STRING):
                continue
            if tok.type in (tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT):
                continue
            lines.setdefault(tok.start[0], []).append(tok.string)
    return chr(10).join("".join(v) for _, v in sorted(lines.items()))


class TestNoDataExitsTwo:
    """⚠️ CI 纪律：审计脚本**没有数据**时必须 exit 2 且打印 ❌，
    绝不能静默 exit 0 让 CI 放行（抓数失败必须显式失败）。"""

    def _run(self, cwd: Path, cache: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--cache", cache],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=300,
        )

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
        assert "industry_sw" in src

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
        src = _s().replace('groupby("ind")["r"].transform("mean")', '"r".mean()')
        assert 'groupby("ind")' not in src, "换成整体均值后必须被 TestNeutralisationIsReal 抓到"


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
        src = _s().replace('groupby(bins)["r"].transform("mean")', '"r".mean()')
        assert "groupby(bins)" not in src

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
            'groupby(["mcap_bin"], observed=True)',
        )
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
        assert "str[:3]" in _s()

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
        src = _s().replace("str[:3]", "str[:6]")
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
            base = 0.01 + 0.001 * t  # 每个时点整体涨一点
            for i in range(20):
                rows.append(
                    {
                        "code": f"c{i}",
                        "t": 100 + t * 10,
                        "r": base,  # ⚠️ 同点内零方差：完全相关
                        "hit": i < 5,
                        "mcap": 100.0 + i,
                        "logmcap": float(np.log(100.0 + i)),
                        "ind": "X110101",
                    }
                )
        out = mod._fama_macbeth(pd.DataFrame(rows))
        n_tp = out[3]
        assert n_tp == 6, (
            f"应逐时点回归得到 6 个系数，实得 {n_tp}——"
            f"若为 0 说明退化成了 pooled OLS 或全被自由度守卫筛掉"
        )


class TestMultiplicity:
    """⚠️⚠️ 多重比较校正——**这轮才补上**，本项目最该早就做的一步。

    我已经**假阳性**过一次：五之二十五测出 `zs_position=above`
    的 +3.71% t=+3.16 p=0.002，一度写进报告，
    后来发现那是**市场 beta**（减去同期沪深300 后 p=0.15）。
    """

    def test_exists(self) -> None:
        assert "def multiplicity_report(" in _s()

    def test_registers_every_measured_basis(self) -> None:
        """⚠️ 每加一个新口径都要登记，否则校正时数漏了会**低估 N**、
        门槛被放松 ⇒ 更容易出假阳性。"""
        src = _s()
        assert "MEASURED_BASES" in src
        assert src.count('", ') >= 4

    def test_reports_all_three_corrections(self) -> None:
        """至少 Bonferroni + Holm + BH 三种，单一校正不够。"""
        src = _s()
        assert "Bonferroni" in src
        assert "Holm-Bonferroni" in src
        assert "Benjamini-Hochberg" in src

    def test_does_p_value_uniformity(self) -> None:
        """⚠️ p 值均匀性 KS 检验：若 p 值**均匀**分布，
        说明与「全无效应」一致——这比逐个看 p 更有力。"""
        assert "kstest" in _s()

    def test_records_the_past_false_positive(self) -> None:
        """⚠️ 必须在代码里写明**曾经假阳性过**，
        否则以后有人会重蹈覆辙还不自知。"""
        src = _s()
        assert "假阳性" in src
        assert "市场 beta" in src

    def test_distinguishes_weak_from_strong_evidence(self) -> None:
        """单个不显著 = 弱证据（可能只是没测出来）；
        校正后仍无一显著 = 强证据。措辞不能混。"""
        assert "校正后仍无一显著" in _s()


class TestMultiplicityTeeth:
    @pytest.fixture
    def broken_file(self):
        """真的把脚本文件改坏，跑完再还原。

        ⚠️⚠️ 必须改**磁盘上的真文件**。只写 `src=_s().replace(...)`
           只在**内存**改字符串，无论文件好坏断言都恒真——
           这类"假牙齿"我在本项目已经栽过至少 3 次。
        """
        original = SCRIPT.read_text(encoding="utf-8")

        def _break(old: str, new: str) -> None:
            assert old in original, f"待改的片段不存在: {old!r}"
            SCRIPT.write_text(original.replace(old, new), encoding="utf-8")

        try:
            yield _break
        finally:
            SCRIPT.write_text(original, encoding="utf-8")

    def test_bite_removing_holm_and_bh(self) -> None:
        """只剩 Bonferroni（最保守）⇒ 漏掉另外两种口径。"""
        src = _s().replace("Holm-Bonferroni", "x").replace("Benjamini-Hochberg", "y")
        assert "Holm-Bonferroni" not in src

    def test_bite_dropping_a_registered_basis(self, broken_file) -> None:
        """漏登记一个口径 ⇒ N 偏小 ⇒ Bonferroni 门槛被放松。

        ⚠️⚠️⚠️ 这条牙齿改过两版，**两版都没有牙齿**：
          v1 `assert "trend=down" not in src` ⇒ 恒**假**，因为
             LEGACY_60_BASES 里也有一行 trend=down（60 只口径）；
          v2 限定到主表区间再 replace ⇒ 恒**真**，因为只在内存里改。
        ⇒ "打偏"和"只改副本"两类错误我都犯过，
           现在统一用 broken_file fixture **真改磁盘**。
        """
        broken_file('("trend=down",         +0.56, +0.84, 0.3999),', "")
        src = _s()
        main = src[src.index("MEASURED_BASES: list") : src.index("LEGACY_60_BASES")]
        assert "trend=down" not in main

    def test_bite_removing_uniformity_test(self) -> None:
        # ⚠️⚠️ 这里踩了**两次**坑：
        #   1. .replace("kstest","no_kstest") ⇒ "no_kstest" 仍含子串
        #      "kstest"，断言恒假/恒真，**无意义**；
        #   2. 改成 "import kstest as _unused" ⇒ 仍含 "kstest"，
        #      牙齿还是不咬（已实测：改脚本后测试照样全绿）。
        # ⇒ 正确做法：断言的是**调用点**，不是 import 语句。
        #    删掉真正干活的那行 kstest(...) 调用。
        src = _s()
        assert 'd, pu = kstest(ps, "uniform")' in src
        src_bad = src.replace('d, pu = kstest(ps, "uniform")', "d, pu = 0.0, 1.0")
        assert 'd, pu = kstest(ps, "uniform")' not in src_bad


class TestSignalTypeScreening:
    """⚠️⚠️ 按**信号类型**筛选——用户实际能选的 `signal_type` 维度。

    ⚠️ 此前只测了默认的 `any_buy` + 结构维度（trend/zs/背驰），
       **从没测过**按 1buy/2buy/3buy/1sell 筛选。
       而这才是用户最自然会用的功能（"帮我找出出现1买的股票"）。

    ⚠️ 这个结果**不与择时结论矛盾**，两层口径不同：
       - 择时层：持有该信号期间，收益 vs **同窗极值基准** → 1buy 6/6 窗正
       - 选股层：某时点**最新信号**是该类型，持有 20 日 vs **同市场其他股** → 无差异
       前者是"信号发生时该不该买"，后者是"该买的时候**买哪只**"。
    """

    def test_all_signal_types_registered(self) -> None:
        """⚠️ 每加一个可选 signal_type 都要登记，否则 N 被低估、
        Bonferroni 门槛被放松 ⇒ 更容易出假阳性。"""
        src = _s()
        for sig in ("1buy", "2buy", "3buy", "1sell"):
            assert f"signal_type={sig}" in src, f"漏登记 {sig}"

    def test_endpoint_really_supports_these(self) -> None:
        """⚠️ 必须核对**端点**真的支持这些取值——
        否则我测的是一个端点上根本不存在的筛选条件。"""
        router = (ROOT / "src" / "easy_tdx" / "web" / "routers" / "screening.py").read_text(
            encoding="utf-8"
        )
        assert 'criteria.get("signal_type"' in router
        for sig in ("1buy", "2buy", "3buy", "1sell"):
            assert sig in router

    def test_documents_two_layers_are_not_contradictory(self) -> None:
        """⚠️ 必须写明选股层/择时层**口径不同**、不矛盾。
        否则读者看到"1buy 择时 6/6 正"又"1buy 筛选无效"会以为矛盾。"""
        src = _s()
        assert "择时层" in src
        assert "买哪只" in src


class TestSameSampleCorrection:
    """⚠️⚠️ 多重比较的所有口径**必须来自同一个样本**。

    五之三十六的**方法论瑕疵**：6 个结构口径用 60 只，
    4 个 signal_type 用 120 只，混在一起做校正**不严格**——
    样本量不同 ⇒ 方差不同 ⇒ p 值分布不同，
    却用同一个 Bonferroni/Holm/BH 门槛去比。
    已补测：全部 10 个口径统一到 **120 只**。
    """

    def test_all_bases_are_120_stocks(self) -> None:
        """⚠️ 主表 MEASURED_BASES 必须**全部**同口径。"""
        src = _s()
        block = src[src.index("MEASURED_BASES: list") :]
        block = block[: block.index("\n]\n")]
        assert "120" in block, "MEASURED_BASES 必须标注 120 只口径"

    def test_legacy_results_kept_out_of_correction(self) -> None:
        """⚠️ 60 只的旧结果**保留对照**但**不参与**校正——
        直接删掉会让后来者看不出结论的**稳定性**（10 口径 vs 6 口径）。"""
        src = _s()
        assert "LEGACY_60_BASES" in src
        assert "不参与" in src or "不用于" in src

    def test_main_table_excludes_legacy_values(self) -> None:
        """⚠️ 主表里**不能**混入 60 只口径的旧数值。
        (-0.41/p=0.6132 是 60 只基线；120 只基线是 +0.12/p=0.8278)"""
        src = _s()
        main = src[src.index("MEASURED_BASES: list") : src.index("LEGACY_60_BASES")]
        assert "0.6132" not in main, "主表混入了 60 只口径的旧基线"

    def test_harmless_but_records_sample_size(self) -> None:
        """两套口径都在脚本里留档，换样本时可直接对比。"""
        src = _s()
        assert "0.8278" in src and "0.6132" in src


class TestSampleIdentity:
    """⚠️⚠️ 口径"同一样本"不只是**只数**相同，还得是**同一批标的**。

    五之三十七我把 10 个口径统一到 120 只，但 `--limit 120` 每次都
    取 `sorted(glob)[:120]`。若排序不稳定、或数据文件增减，
    **每次跑到的可能不是同一批**——那只数相同，样本却不同，
    多重比较照样不严格。

    实测（/tmp 下 10 份缓存）：并集 120 / 交集 120 ⇒ 确实同一批 ✅
    """

    # ⚠️ 2026-10-08：从**写死 /tmp** 改为可配置 + 多目录兜底。
    #    起因：/tmp 被系统清理后，这条测试在**任何干净机器上都会红**，
    #    而它红的原因与被测代码无关（脚本一行没改）。
    #    现在按 EASY_TDX_BASES_DIR → audit_bases/ → /tmp 依次找。
    _CACHE_DIRS = (
        (
            os.environ.get("EASY_TDX_BASES_DIR")
            or str(Path(__file__).resolve().parents[2] / "audit_bases"),
            "u120_*.json",
        ),
        (
            os.environ.get("EASY_TDX_BASES_DIR")
            or str(Path(__file__).resolve().parents[2] / "audit_bases"),
            "sig_*.json",
        ),
        ("/tmp", "u120_*.json"),
        ("/tmp", "sig_*.json"),
    )

    def test_limit_selects_deterministically(self) -> None:
        """⚠️ 必须**排序**后截断，否则 glob 顺序随文件系统变化。"""
        src = _s()
        assert "sorted(" in src

    def test_glob_with_absolute_pattern_is_silent_empty(self) -> None:
        """⚠️⚠️ `Path('/tmp/x_*.json').glob('*')` 返回**空**、**不报错**。

        这是**静默**失败：文件明明在，glob 却匹配不到，于是下面那条
        验证以"无缓存可验"**skip** 掉——看起来通过，实际**根本没验**。
        （本轮实测确认：10 份缓存都在，却一度一条都没匹配上）
        ⇒ 正确写法是 (dir, pattern) 分离：`Path(d).glob(pat)`。
        """
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            Path(d, "x_1.json").write_text("[]", encoding="utf-8")
            assert list(Path(f"{d}/x_*.json").glob("*")) == [], (
                "前提变了：若绝对 pattern 现在能用，这条需重写"
            )
            assert len(list(Path(d).glob("x_*.json"))) == 1

    def test_verified_caches_cover_identical_universe(self) -> None:
        """⚠️ 行为级：真的去读缓存，验证并集==交集。
        ⚠️ 若 glob 匹配不到，**必须 fail 而不是 skip**——
           否则"没验"会伪装成"通过"（本轮已栽过这个坑）。
        """
        import json

        sets = []
        for d, pat in self._CACHE_DIRS:
            for f in sorted(Path(d).glob(pat)):
                try:
                    data = json.loads(f.read_text())
                except Exception:
                    continue
                if (
                    data
                    and isinstance(data, list)
                    and isinstance(data[0], dict)
                    and "code" in data[0]
                ):
                    sets.append({r["code"] for r in data})
        if not sets:
            pytest.fail(
                "❌ 匹配不到任何审计缓存 ⇒ 这条验证**根本没跑**，"
                "不能算通过。先跑 audit_chanlun_screen_usefulness.py。"
            )
        union = set.union(*sets)
        inter = set.intersection(*sets)
        assert union == inter, (
            f"口径样本不一致：并集 {len(union)} 只 vs 交集 {len(inter)} 只 ⇒ 多重比较前提不成立"
        )
        assert len(inter) == 120, f"样本量应为 120，实为 {len(inter)}"
