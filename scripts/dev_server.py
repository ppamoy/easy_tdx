#!/usr/bin/env python3
"""easy_tdx 开发环境启动脚本。

功能：
1. 启动 Python 后端 (FastAPI, port 8000)
2. 启动 Vue 前端 (Vite, port 3012)
3. 监控进程状态

使用：
    python scripts/dev_server.py
"""

import subprocess
import sys
import time
import os


def run_cmd(cmd: list[str], cwd: str | None = None, env: dict | None = None) -> subprocess.Popen:
    """运行命令并返回进程。"""
    full_env = os.environ.copy()
    if env:
        full_env.update(env)
    proc = subprocess.Popen(
        cmd,
        cwd=cwd,
        env=full_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return proc


def main():
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    web_ui_dir = os.path.join(project_root, "web-ui")
    venv_dir = os.path.join(project_root, ".venv")

    print("=" * 60)
    print("easy_tdx 开发环境启动器")
    print("=" * 60)

    # 检查虚拟环境
    python_bin = os.path.join(venv_dir, "bin", "python")
    if not os.path.exists(python_bin):
        print(f"错误: 虚拟环境不存在: {venv_dir}")
        print("请先运行: python -m venv .venv && source .venv/bin/activate && pip install -e .[web]")
        sys.exit(1)

    # 启动后端
    print("\n[1/2] 启动后端服务 (FastAPI, port 8000)...")
    # ⚠️ 不能写 `python -m easy_tdx.cli serve` —— easy_tdx.cli 是**包**不是
    #    模块，实测报 "No module named easy_tdx.cli.__main__"，后端起不来。
    #    正确入口是 uvicorn + easy_tdx.web:create_app（factory 模式）。
    #    加 --reload 让后端源码改动也热重载。
    backend_proc = run_cmd(
        [
            python_bin, "-m", "uvicorn", "easy_tdx.web:create_app",
            "--factory", "--host", "0.0.0.0", "--port", "8000", "--reload",
        ],
        cwd=project_root,
        env={"EASY_TDX_WEB_DIST": os.path.join(web_ui_dir, "dist")},
    )
    time.sleep(2)

    if backend_proc.poll() is not None:
        stdout, stderr = backend_proc.communicate()
        print(f"后端启动失败: {stderr.decode()[:200]}")
        sys.exit(1)

    print("  ✓ 后端已启动 (PID: %d)" % backend_proc.pid)

    # 启动前端
    print("\n[2/2] 启动前端服务 (Vite, port 3012)...")
    node_bin = "node"
    npm_bin = "npm"
    if not os.path.exists(node_bin):
        # 尝试常见位置
        for p in ["/usr/bin/node", "/usr/local/bin/node"]:
            if os.path.exists(p):
                node_bin = p
                npm_bin = p.replace("node", "npm")
                break

    frontend_proc = run_cmd(
        [npm_bin, "run", "dev"],
        cwd=web_ui_dir,
        env={**os.environ, "PORT": "3012"},
    )
    time.sleep(3)

    if frontend_proc.poll() is not None:
        stdout, stderr = frontend_proc.communicate()
        print(f"前端启动失败: {stderr.decode()[:200]}")
        print("尝试安装依赖...")
        install_proc = subprocess.run(
            [npm_bin, "install"],
            cwd=web_ui_dir,
            capture_output=True,
        )
        if install_proc.returncode != 0:
            print(f"依赖安装失败: {install_proc.stderr.decode()[:200]}")
            sys.exit(1)
        frontend_proc = run_cmd(
            [npm_bin, "run", "dev"],
            cwd=web_ui_dir,
            env={**os.environ, "PORT": "3012"},
        )

    print("  ✓ 前端已启动 (PID: %d)" % frontend_proc.pid)

    print("\n" + "=" * 60)
    print("开发环境就绪!")
    print(f"  前端: http://localhost:3012")
    print(f"  API:  http://localhost:8000/api/v1")
    print(f"  文档: http://localhost:8000/redoc")
    print("=" * 60)
    print("\n按 Ctrl+C 停止所有服务")

    try:
        # 等待两个进程
        while True:
            time.sleep(1)
            if backend_proc.poll() is not None:
                print("\n后端进程退出，重新启动...")
                backend_proc = run_cmd(
                    [
                        python_bin, "-m", "uvicorn", "easy_tdx.web:create_app",
                        "--factory", "--host", "0.0.0.0", "--port", "8000", "--reload",
                    ],
                    cwd=project_root,
                )
            if frontend_proc.poll() is not None:
                print("\n前端进程退出，重新启动...")
                frontend_proc = run_cmd(
                    [npm_bin, "run", "dev"],
                    cwd=web_ui_dir,
                    env={**os.environ, "PORT": "3012"},
                )
    except KeyboardInterrupt:
        print("\n正在停止服务...")
        backend_proc.terminate()
        frontend_proc.terminate()
        print("已停止。")


if __name__ == "__main__":
    main()
