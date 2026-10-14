"""CI 里 `e2e-chanlun-render` job 的契约测试。

⚠️ 这条 job 是本轮新加的。加它时我犯了一个**没实跑就提交**的错误：
写成 `python -m easy_tdx.cli serve`，而 `easy_tdx.cli` 是**包**、
没有 `__main__.py`，实跑直接报
  `No module named easy_tdx.cli.__main__; 'easy_tdx.cli' is a package
   and cannot be directly executed`
—— 也就是说这个 job 上到 GitHub 就**必红**，且我本地不会发现。

AGENTS.md §5：能跑真实链路就别只跑单测。本文件把
"CI 里的命令必须在本机实跑验证过"锁成可执行断言。

⚠️ 2026-10-14：本项目**不使用 GitHub Actions**（用户明确确认）。
`.github/workflows/` 已整体删除，故本文件所有用例在 CI 文件不存在时
**跳过**（而非失败）。删除理由与取回方式见
docs/CHANLUN_FIDELITY_AUDIT_V735.md §44。
若将来重新引入 workflow，把文件放回 `.github/workflows/ci.yml`
即可自动恢复这些断言。
"""

from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

CI = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ci.yml"

pytestmark = pytest.mark.skipif(
    not CI.exists(),
    reason=f"项目不使用 GitHub Actions，{CI} 不存在 ⇒ 无 CI 契约可断言（见审计文档 §44）",
)


def _ci() -> dict:
    return yaml.safe_load(CI.read_text(encoding="utf-8"))


def _job() -> dict:
    return _ci()["jobs"]["e2e-chanlun-render"]


def _runs() -> str:
    return "\n".join(s.get("run", "") for s in _job()["steps"])


class TestJobExists:
    def test_job_present(self) -> None:
        assert "e2e-chanlun-render" in _ci()["jobs"]

    def test_runs_on_ubuntu(self) -> None:
        assert _job()["runs-on"] == "ubuntu-latest"

    def test_installs_websockets(self) -> None:
        """脚本靠 websockets 连 CDP，不装会直接 exit 2。"""
        assert "websockets" in _runs()


class TestServeCommandIsReal:
    """⚠️ 本轮实际踩到：`python -m easy_tdx.cli` 对**包**会失败。"""

    def test_does_not_use_python_dash_m(self) -> None:
        runs = _runs()
        assert "python -m easy_tdx.cli" not in runs, (
            "easy_tdx.cli 是包且没有 __main__.py，"
            "`python -m easy_tdx.cli serve` 必失败；必须用 console script"
        )

    def test_uses_console_script(self) -> None:
        assert "easy-tdx serve" in _runs()

    def test_console_script_is_declared(self) -> None:
        """console script 必须在 pyproject 里存在，否则 CI 装完也没有该命令。"""
        pp = (CI.parents[2] / "pyproject.toml").read_text(encoding="utf-8")
        assert 'easy-tdx = "easy_tdx.cli:cli"' in pp


class TestWaitsForServer:
    def test_polls_until_ready(self) -> None:
        runs = _runs()
        assert "seq 1 60" in runs, "必须轮询等待，不能 sleep 一下就假定起来了"

    def test_uses_curl_healthcheck(self) -> None:
        assert "curl -sf http://127.0.0.1:8000/" in _runs()

    def test_fails_loudly_on_timeout(self) -> None:
        runs = _runs()
        assert "服务未就绪" in runs and "exit 1" in runs

    def test_dumps_serve_log_on_failure(self) -> None:
        """启动失败必须能看到原因，否则 CI 只会给一个没头没尾的红叉。"""
        assert "tail -40 /tmp/serve.log" in _runs()


class TestBuildsRealFrontend:
    """⚠️ 必须构建**真实前端产物**，否则测的是个空白页。"""

    def test_installs_node_modules(self) -> None:
        assert "npm ci" in _runs()

    def test_builds_web_ui(self) -> None:
        assert "npm run build" in _runs()

    def test_working_directory_is_web_ui(self) -> None:
        wd = {s.get("working-directory") for s in _job()["steps"]}
        assert "web-ui" in wd


class TestRunsThePixelTest:
    def test_runs_pixel_script(self) -> None:
        assert "scripts/e2e_chanlun_pixels.py" in _runs()

    def test_points_at_the_started_port(self) -> None:
        assert "--base http://127.0.0.1:8000" in _runs()

    def test_script_itself_has_teeth(self) -> None:
        """门禁要能真的红：脚本必须自带牙齿，否则 PASS 可能是空转。"""
        src = (CI.parents[2] / "scripts" / "e2e_chanlun_pixels.py").read_text(encoding="utf-8")
        assert "牙齿" in src and "检测器常真" in src


class TestNoContinueOnError:
    """⚠️ 渲染门禁若 continue-on-error，就等于没有门禁。"""

    def test_job_has_no_continue_on_error(self) -> None:
        assert _job().get("continue-on-error") in (None, False)

    def test_pixel_step_does_not_continue_on_error(self) -> None:
        for s in _job()["steps"]:
            if "e2e_chanlun_pixels.py" in s.get("run", ""):
                assert s.get("continue-on-error") in (None, False), (
                    "像素渲染门禁不能 continue-on-error，否则画歪了也不拦"
                )


class TestDocumentedLimitation:
    def test_records_why_separate_job(self) -> None:
        """必须写清为什么单开一个 job（数据对 ≠ 画出来对）。"""
        c = CI.read_text(encoding="utf-8")
        assert "数据全对而图是错的" in c

    def test_records_why_browser_is_free(self) -> None:
        c = CI.read_text(encoding="utf-8")
        assert "自带 chromium" in c
        assert "playwright" in c
