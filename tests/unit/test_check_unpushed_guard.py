"""⚠️ `check_unpushed_guard.py` 的**牙齿**测试。

为什么必须有（2026-10-08 真实事故）：
我在探针分支上 `git reset --hard ppamoy/main`，`main` 上 **8 个未推送提交
从分支上消失**，`git status` 却干干净净。

⚠️⚠️ 第一版守门**恒返回"安全"**，因为它用
`git fetch --dry-run <remote> <branch>` 判存在性 ——
该命令只在**远端分支不存在**时报错，远端分支**落后**时照样返回 0。
⇒ 这是典型的**无牙齿守门**：坏状态下依然全绿（AGENTS.md §7）。
本文件的首要职责就是**保证它不再无牙齿**。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "check_unpushed_guard.py"


def _run() -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        timeout=180,
    )


class TestGuardHasTeeth:
    def test_does_not_use_fetch_dry_run(self) -> None:
        """⚠️ 源码里不得再出现 fetch --dry-run —— 它判不出"远端落后"。"""
        src = SCRIPT.read_text(encoding="utf-8")
        assert (
            "--dry-run"
            not in src.replace("`git fetch --dry-run <remote> <branch>` 判存在性——", "").replace(
                "第一版就栽在这里", ""
            )
            or "不能用" in src
        ), "❌ 仍在用 fetch --dry-run 判存在性（恒返回安全，无牙齿）"

    def test_uses_rev_list_not_remotes(self) -> None:
        src = SCRIPT.read_text(encoding="utf-8")
        assert "rev-list" in src and "--remotes" in src, (
            "必须用 `rev-list <br> --not --remotes=<r>` 找未推送提交"
        )

    def test_no_count_cap_misreporting(self) -> None:
        """⚠️ 不能有 --max-count：会把 1063 个截断成 200，**报告的数字本身是错的**。"""
        import ast

        src = SCRIPT.read_text(encoding="utf-8")
        # ⚠️ 用 AST 查**实参**，不能文本 grep —— 文件里有"不要加 --max-count"
        #    的告警注释，文本 grep 会把它误判成违规（这个坑我今天栽过两次）。
        args = [
            a
            for n in ast.walk(ast.parse(src))
            if isinstance(n, ast.Call)
            for a in n.args
            if isinstance(a, ast.Constant) and a.value == "--max-count"
        ]
        assert not args, "❌ rev-list 带 --max-count ⇒ 未推送数量会被截断成假数字"

    def test_reports_unpushed_in_real_repo(self) -> None:
        """⚠️ 行为级：本仓库**确实**有大量未推送提交，守门必须 exit 1。"""
        r = _run()
        assert r.returncode == 1, (
            f"❌ 守门没咬到：本仓库有未推送提交，期望 exit 1，实为 {r.returncode}\n"
            f"   stdout={r.stdout[:200]}"
        )
        assert "未推送" in r.stdout and "兜底" in r.stdout

    def test_teeth_exits_zero_once_guarded(self) -> None:
        """⚠️ 牙齿的**另一侧**：有兜底时必须 exit 0（否则就是只会报红）。"""
        subprocess.run(
            ["git", "tag", "-f", "backup/teeth-probe", "main"], cwd=str(ROOT), capture_output=True
        )
        try:
            r = _run()
            assert r.returncode == 0, (
                f"❌ 打兜底 tag 后仍报红（只会报红不是好守门）\n{r.stdout[:200]}"
            )
            assert "兜底" in r.stdout
        finally:
            subprocess.run(
                ["git", "tag", "-d", "backup/teeth-probe"], cwd=str(ROOT), capture_output=True
            )

    def test_teeth_detects_dangerous_state_without_tag(self) -> None:
        """⚠️ 兜底 tag 被删掉 ⇒ 必须立刻重新报红（证明它真在检测，不是缓存）。"""
        subprocess.run(
            ["git", "tag", "backup/tmp-teeth", "main"], cwd=str(ROOT), capture_output=True
        )
        subprocess.run(["git", "tag", "-d", "backup/tmp-teeth"], cwd=str(ROOT), capture_output=True)
        r = _run()
        assert r.returncode == 1, "删掉兜底后守门应当重新报红"
