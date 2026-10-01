#!/usr/bin/env python3
"""playwright 导入与浏览器启动的共享辅助（供 scripts/verify_*.py 使用）。

为什么需要它：playwright 未必装在项目 .venv 里。常见情况有 pip install 到
系统 python（如 ~/.local/lib/python3.11/site-packages）、或 --target=/tmp/pw。
此前各脚本各自硬编码 ``sys.path.insert(0, "/tmp/pw")``，换个环境就 ImportError，
用 ``.venv/bin/python scripts/verify_*.py`` 跑不起来。

统一在这里探测，一次解决。
"""
from __future__ import annotations

import os
import site
import sys

DEFAULT_CHROMIUM = "/usr/bin/chromium"


def import_playwright(auto_reexec: bool = True):
    """导入 playwright，必要时探测常见安装位置。

    当前解释器确实装不了（跨小版本的 C 扩展）时，若 auto_reexec 且找到了可用的
    其它 python，会**自动用那个 python 重跑本脚本**——让
    ``.venv/bin/python scripts/verify_xxx.py`` 也能直接工作。

    Returns:
        ``playwright.sync_api`` 模块

    Raises:
        ImportError: 所有位置都没找到（附带安装提示）
    """
    try:
        from playwright import sync_api  # type: ignore[import-not-found]

        return sync_api
    except ImportError:
        pass

    candidates: list[str] = []
    env_pw = os.environ.get("PLAYWRIGHT_PATH")
    if env_pw:
        candidates.append(env_pw)
    candidates.append("/tmp/pw")

    for attr in ("getusersitepackages", "getsitepackages"):
        fn = getattr(site, attr, None)
        if fn is None:
            continue
        try:
            val = fn()
        except Exception:  # noqa: BLE001
            continue
        if isinstance(val, str):
            candidates.extend(val.split(os.pathsep))
        else:
            candidates.extend(val)

    # 跨版本兜底：项目 .venv 可能是 3.12，而 playwright 装在系统 3.11 的
    # ~/.local/lib 下——上面的 site 查询在 venv 里只返回 3.12 路径，找不到。
    home = os.path.expanduser("~")
    for base in (os.path.join(home, ".local", "lib"), "/usr/local/lib", "/usr/lib"):
        if not os.path.isdir(base):
            continue
        try:
            for entry in sorted(os.listdir(base)):
                # python3.x
                if not entry.startswith("python3."):
                    continue
                for sub in ("site-packages", "dist-packages"):
                    cand = os.path.join(base, entry, sub)
                    if os.path.isdir(os.path.join(cand, "playwright")):
                        candidates.append(cand)
        except OSError:  # noqa: BLE001
            continue

    for path in candidates:
        if path and os.path.isdir(os.path.join(path, "playwright")):
            sys.path.insert(0, path)
            break

    try:
        from playwright import sync_api  # type: ignore[import-not-found]

        return sync_api
    except ImportError as exc:
        if auto_reexec:
            _try_reexec()
        raise ImportError(
            "找不到可导入的 playwright。已探测的位置都不含它，或含但版本不兼容\n"
            "（例如 playwright 装在 python3.11 的 ~/.local/lib 下，而当前用 .venv\n"
            "  的 python3.12 运行——greenlet 等 C 扩展无法跨小版本导入）。\n"
            "解决办法（任选）：\n"
            "  · 用装了 playwright 的那个 python 运行：\n"
            "      python3 scripts/verify_xxx.py      # 系统 python\n"
            "      .venv/bin/python -m pip install playwright   # 或装进 venv\n"
            "  · PLAYWRIGHT_PATH=/path/to/site-packages 指定位置\n"
            "  · pip install playwright --target=/tmp/pw"
        ) from exc


def chromium_path() -> str:
    """浏览器可执行文件路径，可用 CHROMIUM 环境变量覆盖。"""
    return os.environ.get("CHROMIUM", DEFAULT_CHROMIUM)


def launch(sync_api, **kwargs):
    """启动 chromium（默认无沙箱，headless）。"""
    return sync_api.chromium.launch(
        headless=True,
        executable_path=chromium_path(),
        args=["--no-sandbox"],
        **kwargs,
    )


def ui_base() -> str:
    """前端 dev server 地址，可用 EASY_TDX_UI 覆盖。"""
    return os.environ.get("EASY_TDX_UI", "http://127.0.0.1:3012")


def api_base() -> str:
    """后端 API 地址，可用 EASY_TDX_API 覆盖。"""
    return os.environ.get("EASY_TDX_API", "http://127.0.0.1:8000")


def _try_reexec() -> None:
    """当前 python 装不了 playwright 时，找另一个能装的 python 重跑本脚本。

    场景：playwright 装在系统 python3.11，而脚本用项目 .venv 的 python3.12 启动。
    greenlet 等 C 扩展不能跨小版本导入，所以只能在另一个解释器里重跑。
    成功则本进程被替换（不返回）；失败则静默返回，交由调用方报错。
    """
    if os.environ.get("_PW_REEXEC"):
        return  # 已经重跑过一次，别无限递归

    for cand in ("python3", "python3.11", "python3.12", "python3.10"):
        try:
            import subprocess

            probe = subprocess.run(
                [cand, "-c", "import playwright.sync_api"],
                capture_output=True,
                timeout=30,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if probe.returncode != 0:
            continue
        env = dict(os.environ, _PW_REEXEC="1")
        print(f"[ _pw ] 当前解释器缺 playwright，改用 {cand} 重跑", flush=True)
        try:
            import subprocess

            raise SystemExit(
                subprocess.run([cand, *sys.argv], env=env).returncode  # noqa: B604
            )
        except (OSError, subprocess.SubprocessError):
            continue
