"""开发环境启动脚本的牙齿测试。

背景（实测 2026-10-10）：`scripts/dev.sh` 与 `scripts/dev_server.py` 的
**后端启动命令都是坏的**，照原样跑后端根本起不来：

- `dev.sh`       → `easy_tdx.cli.cmd_web:create_app`
                   实测 `AttributeError: Attribute not found`
- `dev_server.py` → `python -m easy_tdx.cli serve`
                   实测 `No module named easy_tdx.cli.__main__`

这两条都是**文档/注释拦不住**的类型：脚本看起来写得很完整，只有真跑才暴露。
所以锁成断言。
"""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DEV_SH = ROOT / "scripts" / "dev.sh"
DEV_PY = ROOT / "scripts" / "dev_server.py"


def test_dev_sh_uses_correct_uvicorn_module():
    """dev.sh 的后端必须经 easy_tdx.web:create_app（--factory --reload）起。

    ⚠️ 别再写成 cmd_web:create_app —— 实测 AttributeError，后端起不来。

    ⚠️ 2026-10-10 二修：dev.sh 里的 uvicorn 命令行已**委托**给
       scripts/dev_backend.sh（否则 dev.sh 会把后端起在 8000，与
       生产 systemd 服务抢端口 ⇒ [Errno 98] address already in use）。
       所以这里不能再断言 dev.sh **自己**含该字符串 —— 那样会逼着
       人把命令行抄回去、又把端口 bug 带回来。
       改为断言「委托关系成立 + 被委托方确实用了正确模块」，两边都锁住。
    """
    assert DEV_SH.is_file(), "scripts/dev.sh 不存在"
    src = DEV_SH.read_text(encoding="utf-8")
    # ① dev.sh 必须委托给 dev_backend.sh（不再自己起 8000）
    assert "dev_backend.sh" in src, (
        "dev.sh 未委托 scripts/dev_backend.sh —— 会直接起在 8000，与生产抢端口"
    )

    # ② 被委托方必须用正确的 factory 入口 + --reload
    backend = ROOT / "scripts" / "dev_backend.sh"
    assert backend.is_file(), "scripts/dev_backend.sh 不存在（dev 后端无处可起）"
    bsrc = backend.read_text(encoding="utf-8")
    assert "easy_tdx.web:create_app" in bsrc, (
        "dev_backend.sh 未使用 easy_tdx.web:create_app —— "
        "cmd_web 里没有 create_app，后端起不来"
    )
    assert "--factory" in bsrc, "create_app 是 factory 模式，缺 --factory 会失败"
    assert "--reload" in bsrc, "dev 后端缺 --reload（改后端代码不会热重启）"


def test_dev_py_does_not_use_broken_module_invocation():
    """dev_server.py 不能写 `python -m easy_tdx.cli`（是包，不能 -m 执行）。"""
    assert DEV_PY.is_file(), "scripts/dev_server.py 不存在"
    src = DEV_PY.read_text(encoding="utf-8")
    assert '"-m", "easy_tdx.cli"' not in src and "'easy_tdx.cli', \"serve\"" not in src, (
        "dev_server.py 仍在用 `python -m easy_tdx.cli` —— "
        "该包没有 __main__，实测 No module named easy_tdx.cli.__main__"
    )
    assert "easy_tdx.web:create_app" in src
    assert "--reload" in src


def test_guard_exempts_long_running_dev_services():
    """守卫必须豁免常驻 dev 服务（uvicorn / vite / resource_tracker）。

    实测 2026-10-10 事故（本文件因此补这条）：
      cron 每 30 分钟跑 reap_stalled_bg.sh --auto，把 dev 后端当"卡死"
      进程杀掉两次（22:00:01、23:00:02），Vite 前端也一起被杀。
      误判链条：
        1. uvicorn --reload 的 resource_tracker / spawn_main 子进程
           天生 CPU 增量=0（只监听 pipe 回收资源）；
        2. 它们命令行含 easy_tdx 路径 ⇒ 命中 DEFAULT_PATTERN；
        3. kill_stalled 用 os.killpg 按**进程组**杀 ⇒ 整组带走。
      后果：reload 期间的请求全部 502，前端只看到裸 502。

    这里不直接 import 该脚本（它顶层就要扫 /proc、且有 CLI 副作用），
    改为在**隔离解释器**里 exec 后取 is_service 判定 —— 与
    AGENTS.md「门禁必须能变红」同款做法。
    """
    import subprocess
    import sys
    import textwrap

    guard = ROOT / "scripts" / "guard_bg_jobs.py"
    assert guard.is_file(), "scripts/guard_bg_jobs.py 不存在"

    code = textwrap.dedent(
        """
        import importlib.util, json, sys
        spec = importlib.util.spec_from_file_location("g", r"%s")
        g = importlib.util.module_from_spec(spec)
        # ⚠️ 必须先注册进 sys.modules：脚本里用了 @dataclass，而 dataclass
        #    解析类型注解时要查 sys.modules[cls.__module__].__dict__。
        #    不注册 ⇒ cls.__module__ 指向尚未注册的 "g" ⇒ 取到 None ⇒
        #    AttributeError: 'NoneType' object has no attribute '__dict__'。
        sys.modules["g"] = g
        spec.loader.exec_module(g)
        # pid=None ⇒ 只测"自己命令行"这条路径（不需要真实进程）
        cases = [
            ("uvicorn easy_tdx.web:create_app --factory --port 8001 --reload", True),
            ("python -c from multiprocessing.resource_tracker import main;main(5)", True),
            ("node /x/node_modules/vite/bin/vite.js --port 3012", True),
            (".venv/bin/python scripts/audit_chanlun_screen_usefulness.py --limit 286", False),
            (".venv/bin/python -m pytest tests/unit -q", False),
        ]
        print(json.dumps([[c, g.is_service(c), want] for c, want in cases]))
        """
        % guard
    )
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=120
    )
    assert out.returncode == 0, f"守卫脚本加载失败: {out.stderr[:500]}"
    import json

    rows = json.loads(out.stdout.strip().splitlines()[-1])
    for cl, got, want in rows:
        assert got == want, f"豁免判定错误: {cl[:60]!r} got={got} want={want}"


def test_dev_sh_frontend_uses_vite_dev_not_build():
    """dev.sh 前端必须起 Vite dev server（热更新），不是 build。"""
    src = DEV_SH.read_text(encoding="utf-8")
    assert "vite" in src.lower(), "dev.sh 前端未使用 vite"
    # 不能是 build（build 是生产产物，没有热更新）
    assert "vite build" not in src


def test_vite_config_proxies_to_dev_backend_not_production():
    """vite 的 /api 代理必须默认指向 dev 后端 8001，**不是**生产的 8000。

    8000 是用户的 user systemd 生产服务（Restart=always，托管 dist 构建
    产物）。开发代理打到它 ⇒ ① 与生产抢端口 ② 改 .vue 看不到变化。
    """
    cfg = ROOT / "web-ui" / "vite.config.ts"
    assert cfg.is_file(), "web-ui/vite.config.ts 不存在"
    src = cfg.read_text(encoding="utf-8")
    assert "/api" in src and "proxy" in src, "vite 未配 /api 代理"
    # 模板串 `http://127.0.0.1:${devApiPort}` + 默认 '8001'
    assert "devApiPort" in src, "代理端口未抽成变量"
    assert "'8001'" in src or '"8001"' in src, (
        "VITE_API_PORT 默认值不是 8001 —— 会打到生产 8000"
    )


def test_dev_sh_backend_must_not_bind_production_port():
    """dev.sh 的后端**不能**起在 8000 —— 那是生产 systemd 服务在用的端口。

    实测 2026-10-10：原 dev.sh 用 `BACKEND_PORT=8000` 直接 `uvicorn`，
    而 8000 已被 `easy-tdx.service`（Restart=always）占用，结果：
        ERROR: [Errno 98] error while attempting to bind ...
        address already in use
    后端根本起不来 ⇒ 前端所有 /api 请求拿不到后端 ⇒ 满屏报错。

    另外 8000 托管的是 `web-ui/dist`（构建产物），就算起得来也看不到
    .vue 的改动。所以这里锁死：**dev.sh 里 8000 只能作为"别碰"的注释
    存在，不能作为后端监听端口生效**。
    """
    src = DEV_SH.read_text(encoding="utf-8")
    # 去掉注释行后，不应再出现把后端绑定到 8000 的写法
    code_lines = [
        ln for ln in src.splitlines()
        if not ln.lstrip().startswith("#")
    ]
    code = "\n".join(code_lines)
    assert "--port \"$BACKEND_PORT\"" not in code, (
        "dev.sh 仍会把后端绑定到 BACKEND_PORT(=8000)，与生产服务抢端口"
    )
    assert "uvicorn" not in code, (
        "dev.sh 不应再自己拼 uvicorn 命令行 —— 请委托 scripts/dev_backend.sh（8001）"
    )


def test_dev_backend_script_uses_dev_port_and_no_dist():
    """scripts/dev_backend.sh 必须用独立端口且不清空不了 dist 托管。

    两条硬要求：
    1. 默认端口 8001（非 8000）—— 不与生产服务抢端口；
    2. EASY_TDX_WEB_DIST 置空 —— dev 后端不该托管生产构建产物。
    """
    script = ROOT / "scripts" / "dev_backend.sh"
    assert script.is_file(), "scripts/dev_backend.sh 不存在（dev 后端无处可起）"
    src = script.read_text(encoding="utf-8")
    assert "8001" in src, "dev_backend.sh 默认端口不是 8001"
    assert "EASY_TDX_WEB_DIST" in src, "未显式处理 EASY_TDX_WEB_DIST"
    assert "--reload" in src, "dev 后端缺 --reload"
