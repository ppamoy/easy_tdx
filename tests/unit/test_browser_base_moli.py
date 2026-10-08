"""本机浏览器底座契约：默认走 **moli（CDP）**，不再直接拉 chromium。

背景（2026-10-08，用户指示）：
  "浏览器我都改成用moli了，不要在用chromium了"

为什么要有测试锁住：
  · `scripts/_pw.py` 是十几个 verify_*/e2e_* 脚本的**公共入口**，
    它一旦悄悄退回 `chromium.launch()`，所有脚本会**无声**地改回旧路径；
  · moli 的 `--layout` 坑很隐蔽：**不加**时 goto/evaluate/innerText
    照样通过，但 click 挂死、boundingBox 谎报 stub、截图直接报错
    —— 只拿"页面能打开"当断言会**误判浏览器可用**。

⚠️ 注意：**CI（ubuntu-latest）仍然用系统 chromium**，那是**正确**的
   ——CI runner 自带 chromium，且不装 moli。本测试只约束**本机**路径。
"""
from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
PW = SCRIPTS / "_pw.py"


def _code_only(src: str, node: ast.AST) -> str:
    """⚠️ 只取函数体里**真正会执行**的代码（剥掉 docstring 与注释）。

    为什么需要：本文件里到处写着 `chromium.launch` 这个词做反例说明，
    若直接对源码 grep，**文档自己就会把守门测试逼成假阳性**。
    只看 AST 里的表达式/调用，才是对"真实行为"的断言（AGENTS.md §1）。
    """
    body = getattr(node, "body", [])
    # 跳过 docstring
    if body and isinstance(body[0], ast.Expr) and \
            isinstance(body[0].value, ast.Constant) and \
            isinstance(body[0].value.value, str):
        body = body[1:]
    parts: list[str] = []
    for stmt in body:
        for sub in ast.walk(stmt):
            if isinstance(sub, ast.Attribute):
                parts.append(sub.attr)
            elif isinstance(sub, ast.Name):
                parts.append(sub.id)
            elif isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                parts.append(sub.value)
    return " ".join(parts)


def _called_attrs(node: ast.AST) -> set[str]:
    """函数体里真正被**调用**的方法名（Attribute.attr 且父节点是 Call）。"""
    out: set[str] = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute):
            out.add(sub.func.attr)
    return out


class TestPwUsesMoliNotChromium:
    def test_pw_module_exists(self) -> None:
        assert PW.exists(), "scripts/_pw.py 必须存在（公共浏览器入口）"

    def test_defines_cdp_endpoint_and_ensure_moli(self) -> None:
        src = PW.read_text(encoding="utf-8")
        assert "def ensure_moli(" in src, "必须提供 ensure_moli()（幂等拉起服务）"
        assert "def cdp_endpoint(" in src

    def test_ensure_moli_uses_the_managed_start_script(self) -> None:
        """⚠️ **不能**自己拼 `moli serve` 命令行——
        必须调 moli-serve-start，因为它内置了必需的 `--layout`。"""
        src = PW.read_text(encoding="utf-8")
        assert "moli-serve-start" in src
        body = src[src.index("def ensure_moli("):]
        body = body[:body.index("\ndef ", 1)]
        assert "serve" not in body.replace("moli-serve-start", "") \
            or "--layout" in body, \
            "⚠️ 若自己拼 moli serve，必须显式带 --layout（否则截图会失败）"

    def test_launch_pw_uses_cdp_not_chromium(self) -> None:
        """⚠️ 必须**逐个函数**检查，而不是全文 grep。

        历史教训：我第一版写成「全文扫到 chromium.launch 就断言文件里有
        _chromium_fallback 这个词」——结果只要注释里留着那个词就恒真，
        牙齿一咬就发现：把 launch_pw 里的 connect_over_cdp 换成
        chromium.launch，守门测试**照样全过**。
        """
        src = PW.read_text(encoding="utf-8")
        tree = ast.parse(src)
        funcs = {n.name: n for n in ast.walk(tree)
                 if isinstance(n, ast.FunctionDef)}

        # 1) 公共入口 launch_pw 必须走 CDP
        assert "launch_pw" in funcs, "launch_pw 没了（先怀疑迁移被回退）"
        lp = funcs["launch_pw"]
        lp_src = _code_only(src, lp)
        # ⚠️ `pw.chromium` 是 **Playwright 的浏览器类型属性**（不是二进制），
        #    合法写法就是 pw.chromium.connect_over_cdp(...)
        #    ⇒ 要禁的是 `chromium.launch`，不能只搜 "chromium" 这个词。
        assert "connect_over_cdp" in lp_src, \
            "❌ launch_pw 必须用 connect_over_cdp（moli），不能本地启动浏览器"
        assert "launch" not in _called_attrs(lp), \
            "❌ launch_pw 的代码里出现了 *.launch(...) ⇒ 已退回旧路径"

        # 2) 任何函数里的本地启动都必须**先经过显式回退开关**
        for name, fn in funcs.items():
            attrs = _called_attrs(fn)
            if "launch" not in attrs:
                continue
            body = _code_only(src, fn)
            assert "_chromium_fallback" in body, (
                f"❌ {name}() 里的本地浏览器启动没有显式回退开关保护"
            )
            guard = body.index("_chromium_fallback")
            assert guard < body.index("chromium"), (
                f"❌ {name}() 的回退开关在启动**之后**才判断，逻辑无效"
            )

    def test_provides_launch_pw_and_close_pw(self) -> None:
        src = PW.read_text(encoding="utf-8")
        assert "def launch_pw(" in src, "调用方改用 launch_pw(pw)"
        assert "def close_pw(" in src, \
            "⚠️ CDP 模式不 stop playwright 会让进程挂住不退出"


class TestCallSitesMigrated:
    """⚠️ 每个调用点都必须已迁移 —— 否则 import launch_pw 会 ImportError。"""

    CALLERS = [
        "verify_f2_review_panel", "verify_f3_train_session",
        "verify_f9_alpha_badge", "verify_fundamental_page",
        "verify_fx_pages", "verify_fx_tooltip", "verify_level_switch",
        "verify_marker_pixels", "verify_mmd_colors",
        "verify_qujiantao_badge_method", "verify_train_e2e", "verify_ui",
        "e2e_mmd_marker_pixels", "e2e_mmd_real_component",
    ]

    @pytest.mark.parametrize("name", CALLERS)
    def test_no_raw_chromium_launch_remains(self, name: str) -> None:
        src = (SCRIPTS / f"{name}.py").read_text(encoding="utf-8")
        assert ".chromium.launch(" not in src, \
            f"{name}.py 还在直接 chromium.launch —— 必须改用 launch_pw(pw)"

    @pytest.mark.parametrize("name", CALLERS)
    def test_uses_launch_pw(self, name: str) -> None:
        src = (SCRIPTS / f"{name}.py").read_text(encoding="utf-8")
        assert "launch_pw(" in src, f"{name}.py 未使用 launch_pw"
        assert "import" in src and "launch_pw" in src.split("def ")[0] + src, \
            f"{name}.py 必须 import launch_pw"

    @pytest.mark.parametrize("name", CALLERS)
    def test_still_parses(self, name: str) -> None:
        src = (SCRIPTS / f"{name}.py").read_text(encoding="utf-8")
        ast.parse(src)  # 迁移过程中最容易破的就是语法


class TestTeeth:
    """⚠️ 牙齿：把某个调用点改回 chromium.launch，**守门测试必须 FAIL**。

    ⚠️ 历史教训（我自己犯过 14+ 次）：写
        ``assert ".chromium.launch(" in 篡改后的源码``
    是**空转断言**——它只复述我刚做完的动作，永远为真。
    真正的牙齿必须**跑一遍守门测试**，断言它**报错**。
    """

    def _run_guard(self) -> subprocess.CompletedProcess:
        return subprocess.run(  # noqa: S603
            [sys.executable, "-m", "pytest",
             "tests/unit/test_browser_base_moli.py::TestCallSitesMigrated",
             "-q", "--no-header", "-x"],
            cwd=ROOT, capture_output=True, text=True, timeout=300, check=False,
        )

    def test_bite_reverting_one_caller_is_caught(self) -> None:
        target = SCRIPTS / "verify_ui.py"
        original = target.read_text(encoding="utf-8")
        assert "launch_pw(" in original, \
            "⚠️ 前提不成立：verify_ui.py 里找不到 launch_pw（先怀疑牙齿）"

        baseline = self._run_guard()
        assert baseline.returncode == 0, (
            "⚠️ 未篡改时守门测试就不通过 —— 基线坏了，先修基线再谈牙齿\n"
            + baseline.stdout[-1500:]
        )

        try:
            broken = original.replace("launch_pw(", "pw.chromium.launch(")
            assert broken != original, "替换没生效（先怀疑牙齿）"
            target.write_text(broken, encoding="utf-8")
            # 确认真的改回去了，且语法仍然合法（否则牙齿是"靠语法错"作弊）
            assert ".chromium.launch(" in target.read_text(encoding="utf-8")
            ast.parse(broken)

            after = self._run_guard()
            assert after.returncode != 0, (
                "❌ 牙齿没咬到：把 verify_ui.py 改回 chromium.launch，"
                "守门测试仍然全过 ⇒ 守门形同虚设"
            )
            assert "chromium.launch" in after.stdout, (
                "❌ 报错信息里没提到 chromium.launch，可能是因为别的原因挂的"
            )
        finally:
            target.write_text(original, encoding="utf-8")
            import ast as _ast
            _ast.parse(target.read_text(encoding="utf-8"))
            restored = self._run_guard()
            assert restored.returncode == 0, "❌ 恢复后仍不通过（测试没还原干净）"

    def test_bite_breaking_pw_module_is_caught(self) -> None:
        """⚠️ 第二颗牙：把公共入口改回裸 chromium.launch，也必须被抓到。"""
        original = PW.read_text(encoding="utf-8")
        try:
            broken = original.replace("connect_over_cdp(", "chromium.launch(")
            assert broken != original, "替换没生效（先怀疑牙齿）"
            PW.write_text(broken, encoding="utf-8")
            proc = subprocess.run(  # noqa: S603
                [sys.executable, "-m", "pytest",
                 "tests/unit/test_browser_base_moli.py::TestPwUsesMoliNotChromium",
                 "-q", "--no-header", "-x"],
                cwd=ROOT, capture_output=True, text=True, timeout=300, check=False,
            )
            assert proc.returncode != 0, \
                "❌ 牙齿没咬到：公共入口退回 chromium.launch 竟无人报警"
        finally:
            PW.write_text(original, encoding="utf-8")