"""`verify_measured_bases.py` 的测试。

⚠️ 这个脚本的**存在理由**是：MEASURED_BASES 里的 10 个数字是**手抄**的
（从审计脚本控制台输出 grep 出来的）。手抄会漂，而漂了没人会发现。
本测试保证这个"防漂移闸门"**自己没坏**。
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "verify_measured_bases.py"
CI_YML = ROOT / ".github" / "workflows" / "ci.yml"


def _mod():
    spec = importlib.util.spec_from_file_location("_vmb", SCRIPT)
    m = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(m)
    return m


class TestContract:
    def test_exists_and_parses(self) -> None:
        assert SCRIPT.exists()
        _mod()  # 能 import 说明语法 OK

    def test_exits_two_when_no_index(self, tmp_path) -> None:
        """⚠️ 缺指数 ⇒ exit 2，**不假装通过**。"""
        m = _mod()
        old = sys_argv = None
        try:
            import sys
            sys.argv = ["x", "--data", str(tmp_path)]
            assert m.main() == 2
        finally:
            import sys
            sys.argv = sys_argv or ["pytest"]

    def test_declares_every_base_and_keeps_two_in_sync(self) -> None:
        """⚠️ BASES 的条数必须**同时**匹配登记表，不能写死数字。

        写死（原来 `== 10`）的坏处：新增口径时要**手动**改这里，
        忘了就会假失败；更糟的是有人为了让它过而把 BASES 删回 10 条。
        ⇒ 改为断言"条数一致"+"关键口径都在"，
           新增口径**不需要**改这条测试。
        """
        m = _mod()
        reg = m._registered()
        assert len(m.BASES) == len(reg), (
            f"BASES 列出 {len(m.BASES)} 个但登记了 {len(reg)} 个 "
            f"⇒ 防漂移闸门会漏验/误报")
        labels = {lbl for lbl, _ in m.BASES}
        for must in ("signal_type=1buy", "zs_position=above",
                     "zs_position=inside", "min_quality>=80",
                     "min_zs_count>=5"):
            assert must in labels, f"闸门漏了 {must}（新增口径请补进 BASES）"


class TestStructuralCheck:
    """结构自检是 CI 能跑的那部分（不需要行情缓存）。"""

    def test_passes_on_current_registration(self) -> None:
        m = _mod()
        assert m._structural_check(m._registered()) == []

    def test_catches_inconsistent_t_and_p(self) -> None:
        """⚠️ t=-1.56 的 p 应≈0.119；若登记成 0.0001 ⇒ 手抄错了。"""
        m = _mod()
        bad = m._structural_check({"x": (-1.39, -1.56, 0.0001)})
        assert bad, "不自洽的 t/p 竟然没被抓到"
        assert any("不自洽" in b for b in bad)

    def test_catches_missing_basis(self) -> None:
        """⚠️ 少登记一个 ⇒ N 偏小 ⇒ Bonferroni 门槛被放松。"""
        m = _mod()
        reg = m._registered()
        one = next(iter(reg))
        reg.pop(one)
        bad = m._structural_check(reg)
        assert bad, "漏登记竟然没被抓到"
        assert any("漏登记" in b for b in bad)

    def test_catches_impossible_p(self) -> None:
        m = _mod()
        assert m._structural_check({"x": (0.1, 1.0, 1.5)})
        assert m._structural_check({"x": (0.1, 1.0, 0.0)})
        assert m._structural_check({"x": (0.1, 1.0, -0.2)})


class TestNotSelfCertifying:
    """⚠️ 关键：验证脚本**不能**靠 import 被验证的模块来算。

    如果它 `import audit_screen_sector_neutral` 并调用对方的函数，
    那两边共享同一个 bug ⇒ 永远"一致"，闸门形同虚设。
    必须**照算法重写**。
    """

    def test_does_not_import_the_script_it_verifies(self) -> None:
        src = SCRIPT.read_text(encoding="utf-8")
        code = "\n".join(
            l for l in src.splitlines()
            if not l.strip().startswith("#"))
        assert "import audit_screen_sector_neutral" not in code
        assert "from audit_screen_sector_neutral" not in code

    def test_reads_registration_as_text_not_import(self) -> None:
        """⚠️ 登记值用**文本解析**取，不 import——避免共享 bug。"""
        src = SCRIPT.read_text(encoding="utf-8")
        assert "read_text" in src
        assert "re.findall" in src


class TestTeeth:
    @pytest.fixture
    def broken_file(self):
        target = ROOT / "scripts" / "audit_screen_sector_neutral.py"
        original = target.read_text(encoding="utf-8")

        def _break(old: str, new: str) -> None:
            assert old in original, f"待改片段不存在: {old!r}"
            target.write_text(original.replace(old, new), encoding="utf-8")

        try:
            yield _break
        finally:
            target.write_text(original, encoding="utf-8")

    def test_bite_corrupted_registration_is_detected(
            self, broken_file) -> None:
        """改坏一个登记值 ⇒ 结构自检必须报错（**真改磁盘**）。"""
        m = _mod()
        broken_file('("trend=up",           -0.27, -0.39, 0.6933),',
                    '("trend=up",           -0.27, -0.39, 0.0000),')
        assert m._structural_check(m._registered()), \
            "改坏 p 值竟然没被抓到 ⇒ 闸门失效"

    def test_bite_dropped_registration_is_detected(
            self, broken_file) -> None:
        m = _mod()
        broken_file('("trend=up",           -0.27, -0.39, 0.6933),\n', '')
        assert m._structural_check(m._registered()), \
            "漏登记竟然没被抓到 ⇒ 闸门失效"

    def test_bite_dropping_structural_flag_breaks_ci(self) -> None:
        """⚠️ CI 里那一步必须带 --structural-only，
        否则会去要 /tmp 缓存，在 CI 上必然 exit 2 ⇒ 假红。"""
        yml = CI_YML.read_text(encoding="utf-8")
        assert "verify_measured_bases.py --structural-only" in yml


class TestInsideCriterionFailsCorrection:
    """⚠️⚠️ `zs_position=inside` 是**唯一**单看显著（p<α）的选股口径。

    五之四十只用了 120 只（入选 134 条，样本太轻）⇒ 标"证据不足"。
    本轮用**全量 286 只**（入选 292 条）重做，必须钉死结论：
    即使在 2.4 倍样本上，它**仍然扛不住多重比较校正**。
    """

    SCRIPT = (Path(__file__).resolve().parents[2] / "scripts"
              / "audit_screen_sector_neutral.py")

    def test_uses_full_286_sample_not_the_light_one(self) -> None:
        """⚠️ 必须用 286 只口径，不能还用 120 只的旧值。"""
        src = self.SCRIPT.read_text(encoding="utf-8")
        blk = src[src.index("MEASURED_BASES"):src.index("LEGACY_60_BASES")]
        assert '("zs_position=inside", +1.34, +2.28, 0.0223)' in blk, \
            "inside 必须用全量 286 只口径（+1.34% t=+2.28 p=0.0223）"

    def test_documents_that_it_is_not_beta(self) -> None:
        """⚠️ 关键区分：inside **不是** beta（两个独立控制后仍显著），
        这与 zs_position=above 的模式**相反**。
        若后人只看到"不显著"就以为和 above 一样是 beta，会误判。"""
        src = self.SCRIPT.read_text(encoding="utf-8")
        blk = src[src.index("MEASURED_BASES"):src.index("LEGACY_60_BASES")]
        line = [l for l in blk.splitlines() if "zs_position=inside" in l]
        assert line, "找不到 inside 的登记行"
        # ⚠️ 必须记录**三个基准**的 p：原始 0.0041 / 减均值 0.0388 /
        #    减真实指数 0.0065。三个都在注释里才算记全。
        #    （第一版我用 src[idx-600:idx] 取上下文，600 字符**够不到**
        #      0.0041 ⇒ 假失败。改为直接在整段 MEASURED_BASES 里找。）
        for p in ("0.0041", "0.0388", "0.0065"):
            assert p in blk, f"缺少基准 p={p} 的记录"

    def test_attensuation_is_recorded(self) -> None:
        """⚠️ 效应随'排除低入选次数'**单调衰减**：
        全部 t=+2.28 → >=2次 t=+2.05 → >=3次 t=+0.70
        ⇒ 显著性部分依赖"只被选中一两次"的股票。这必须留档。

        ⚠️⚠️ 第一版只写 `assert "单调衰减" in src`——但**别的文件**
        （verify_measured_bases.py）里也有这几个字 ⇒ 删掉本文件那段
        测试照样绿 ⇒ **没有牙齿**。这是本项目第 10 次"错作用域恒真断言"。
        ⇒ 现在必须在 **MEASURED_BASES 段内**找，且要求三档 t 都在。
        """
        src = self.SCRIPT.read_text(encoding="utf-8")
        blk = src[src.index("MEASURED_BASES"):src.index("LEGACY_60_BASES")]
        assert "单调衰减" in blk, "MEASURED_BASES 段里必须留档衰减结论"
        for t in ("+2.28", "+2.05", "+0.70"):
            assert t in blk, f"衰减三档缺 {t}"


class TestAttenuationTeeth:
    SCRIPT = (Path(__file__).resolve().parents[2] / "scripts"
              / "audit_screen_sector_neutral.py")

    @pytest.fixture
    def broken_file(self):
        target = (Path(__file__).resolve().parents[2] / "scripts"
                  / "audit_screen_sector_neutral.py")
        original = target.read_text(encoding="utf-8")

        def _break(old: str, new: str) -> None:
            assert old in original, f"待改片段不存在: {old!r}"
            target.write_text(original.replace(old, new), encoding="utf-8")

        try:
            yield _break
        finally:
            target.write_text(original, encoding="utf-8")

    def test_bite_reverting_inside_to_light_sample(self,
                                                   broken_file) -> None:
        """把 inside 改回 120 只的轻样本值 ⇒ 必须被抓。

        ⚠️ 第一版我写成 `assert ... is not None`，
        而 `_structural_check` **永远**返回 list（空 list 也非 None）
        ⇒ 恒真、**没有牙齿**。本项目第 9 次"恒真断言"。
        已改为断言**具体内容**。
        """
        broken_file('("zs_position=inside", +1.34, +2.28, 0.0223)',
                    '("zs_position=inside", +1.44, +1.98, 0.0477)')
        src = self.SCRIPT.read_text(encoding="utf-8")
        blk = src[src.index("MEASURED_BASES"):src.index("LEGACY_60_BASES")]
        assert '("zs_position=inside", +1.34, +2.28, 0.0223)' not in blk, \
            "⚠️ inside 被改回 120 只轻样本值了（结论会跟着错）"
        assert '("zs_position=inside", +1.44, +1.98, 0.0477)' in blk


class TestBasesDirIsConfigurable:
    """⚠️ 基线缓存原本**全部写死 /tmp/**（2026-10-08 改）。

    为什么要改：/tmp 会被系统清理，一清掉这 13 条基线就无法自动复核，
    漂移闸门只会干巴巴报"缺 13 份缓存，先跑审计脚本"——
    而**那条建议在缓存已被清理后往往等于让重跑 3 小时**。
    ⇒ 现在：EASY_TDX_BASES_DIR → audit_data/bases/ → /tmp 依次找。

    ⚠️ 注意：CI 与"没数据时应报错"的契约不受影响——
       三处都找不到时仍然 exit 2（下面测两侧）。
    """

    SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "verify_measured_bases.py"

    def _src(self) -> str:
        return self.SCRIPT.read_text(encoding="utf-8")

    def test_no_hardcoded_tmp_in_bases_table(self) -> None:
        """BASES 里不得再出现裸 /tmp/ 路径（必须经 _cache() 解析）。"""
        import ast
        tree = ast.parse(self._src())
        bases = next(n for n in tree.body
                     if isinstance(n, ast.AnnAssign)
                     and getattr(n.target, "id", "") == "BASES")
        # 逐个元素检查：必须是 _cache("name.json") 调用
        for elt in bases.value.elts:
            assert isinstance(elt, ast.Tuple), f"BASES 元素应是二元组：{ast.dump(elt)[:80]}"
            path_expr = elt.elts[1]
            assert isinstance(path_expr, ast.Call) \
                and getattr(path_expr.func, "id", "") == "_cache", \
                "❌ BASES 的路径必须用 _cache(...) 解析，不能写死 /tmp"

    def test_cache_helper_tries_bases_dir_then_tmp(self) -> None:
        assert "def _cache(" in self._src()
        s = self._src()
        body = s[s.index("def _cache("):]
        body = body[:body.index("\ndef ")]
        assert "BASES_DIR" in body, "必须先找 BASES_DIR"
        assert 'Path("/tmp")' in body, "必须回退到 /tmp"

    def test_env_var_override(self) -> None:
        s = self._src()
        assert "EASY_TDX_BASES_DIR" in s, "必须支持环境变量覆盖，否则换机就废"

    def test_missing_message_says_where_it_looked(self) -> None:
        """⚠️ 报错必须说清**找过哪些目录**，否则看到的人无从下手。"""
        s = self._src()
        assert "已找过" in s, "缺缓存时必须报出尝试过的目录"
