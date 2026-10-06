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

        ⚠️ 后来加了市值口径，这句也跟着更新——测试**过期**和测试
        **失效**一样都要修，不能放着。"""
        src = _s()
        assert "中性化后仍选不出超额" in src

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
        assert "行业+市值中性化后仍选不出超额" in _s()


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
        assert "行业+市值中性化后仍选不出超额" in _s()


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
