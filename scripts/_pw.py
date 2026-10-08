#!/usr/bin/env python3
"""playwright 导入与浏览器启动的共享辅助（供 scripts/verify_*.py 使用）。

⚠️ 2026-10-08 起**默认走 moli（CDP）**，不再直接启动 /usr/bin/chromium。
   理由见本文件底部「为什么不再用 chromium」。

为什么需要本模块：playwright 未必装在项目 .venv 里。常见情况有 pip install 到
系统 python（如 ~/.local/lib/python3.11/site-packages）、或 --target=/tmp/pw。
此前各脚本各自硬编码 ``sys.path.insert(0, "/tmp/pw")``，换个环境就 ImportError，
用 ``.venv/bin/python scripts/verify_*.py`` 跑不起来。

统一在这里探测，一次解决。
"""
from __future__ import annotations

import os
import site
import subprocess
import sys

# ⚠️ moli 的 CDP 端点（Playwright connectOverCDP 用）
DEFAULT_CDP = "http://127.0.0.1:9222"
MOLI_SERVE_START = os.path.expanduser("~/.local/bin/moli-serve-start")

# 仅在显式要求回退时才用的本地 chromium（默认**不**走）
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


def cdp_endpoint() -> str:
    """moli 的 CDP 端点，可用 MOLI_CDP 环境变量覆盖。"""
    return os.environ.get("MOLI_CDP", DEFAULT_CDP)


def ensure_moli(endpoint: str | None = None) -> str:
    """确保 moli serve 在跑（幂等），返回 CDP 端点。

    ⚠️ 必须带 ``--layout``：不加时 moli 走 "deterministic compatibility
    geometry"，后果是 click 超时挂死、boundingBox() 谎报 stub 尺寸、
    screenshot 直接报 "renderer layout is disabled"——而 goto/evaluate/
    innerText 照样通过，**只拿这些断言就会误判浏览器可用**。
    ``moli-serve-start`` 已内置该 flag，这里只调用它。
    """
    ep = endpoint or cdp_endpoint()
    url = ep.replace("http://", "").replace("https://", "")
    host, _, port = url.partition(":")
    port = port or "9222"
    probe = f"http://{host}:{port}/json/version"

    def alive() -> bool:
        try:
            r = subprocess.run(  # noqa: S603
                ["curl", "-sf", "-m", "3", probe],
                capture_output=True, timeout=5, check=False,
            )
            return r.returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False

    if alive():
        return ep
    if not os.path.exists(MOLI_SERVE_START):
        raise RuntimeError(
            f"moli 未在 {probe} 服务，且找不到启动脚本 {MOLI_SERVE_START}\n"
            "请手动执行：~/.local/bin/moli-serve-start"
        )
    subprocess.run([MOLI_SERVE_START], check=True, timeout=60)  # noqa: S603
    if not alive():
        raise RuntimeError(f"moli-serve-start 执行后 {probe} 仍不可用")
    return ep


def chromium_path() -> str:
    """⚠️ 仅供**回退**用：本地 chromium 可执行文件路径。

    保留这个函数是因为十几个 verify_*/e2e_* 脚本还在 import 它。
    浏览器本身请改用 :func:`launch`（走 moli）。
    """
    return os.environ.get("CHROMIUM", DEFAULT_CHROMIUM)


def launch(sync_api, **kwargs):
    """连上 **moli**（CDP）并返回 ``(browser, playwright)``。

    ⚠️ 与旧版不同：CDP 模式下 playwright 必须由
    ``sync_playwright().start()`` 创建，且**不能**提前关闭，
    否则 browser 会跟着断。返回 playwright 让调用方负责收尾：

        browser, pw = launch(sync_api)
        try:
            ...
        finally:
            browser.close()
            pw.stop()          # ⚠️ 必须 stop，否则进程不退出

    保留 ``**kwargs`` 形参只为兼容旧调用方；CDP 模式下
    ``headless`` / ``executable_path`` / ``args`` **不再生效**
    （浏览器早已由 moli-serve-start 拉起）。
    """
    if kwargs.get("_chromium_fallback"):
        kwargs.pop("_chromium_fallback")
        return sync_api.chromium.launch(  # type: ignore[no-any-return]
            headless=True, executable_path=chromium_path(), args=["--no-sandbox"],
        )
    endpoint = ensure_moli()
    pw = sync_api.sync_playwright().start()
    browser = pw.chromium.connect_over_cdp(endpoint)
    return browser, pw  # type: ignore[return-value]


def new_page(browser):
    """在 moli 上开一个新 page（复用已有 context 以共享 profile）。"""
    ctx = browser.contexts[0] if browser.contexts else browser.new_context()
    return ctx, ctx.new_page()


def launch_pw(pw, **kwargs):
    """替代旧的「直接启动本地浏览器」写法的 drop-in。

    老调用点形如::

        browser = pw.chromium.launch(headless=True, executable_path=..., args=[...])

    现在请改成::

        browser = launch_pw(pw)

    ``headless`` / ``executable_path`` / ``args`` 会被**忽略**——
    浏览器已由 moli-serve-start 拉起，CDP 模式下无从控制这些。
    保留 ``**kwargs`` 纯粹是为了让老调用点**不必立刻删参数**。

    ⚠️ 若用 ``with sync_playwright() as pw:``，退出 with 时会自动 stop，
    无需额外收尾；若是 ``sync_playwright().start()``，必须配
    :func:`close_pw`，否则进程挂住不退出。
    """
    endpoint = ensure_moli()
    return pw.chromium.connect_over_cdp(endpoint)


def close_pw(browser, pw=None) -> None:
    """收尾：关 browser；若 pw 来自 ``sync_playwright().start()`` 还要 stop。

    ⚠️ **不 stop 会让进程挂住不退出**——这是 CDP 模式最容易踩的坑。
    """
    try:
        browser.close()
    except Exception:  # noqa: BLE001
        pass
    if pw is not None:
        try:
            pw.stop()
        except Exception:  # noqa: BLE001
            pass


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
