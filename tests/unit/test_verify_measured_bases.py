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

    def test_declares_all_ten_bases(self) -> None:
        m = _mod()
        assert len(m.BASES) == 10
        labels = {lbl for lbl, _ in m.BASES}
        assert "signal_type=1buy" in labels
        assert "zs_position=above" in labels


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
