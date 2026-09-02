#!/usr/bin/env python3
"""检查 easy_tdx 项目状态并运行关键测试。"""

import subprocess
import sys
import os

def run_cmd(cmd: str, cwd: str = None) -> tuple[int, str, str]:
    """运行命令并返回 (returncode, stdout, stderr)."""
    result = subprocess.run(
        cmd, shell=True, capture_output=True, text=True, cwd=cwd or "/home/skp/workspace/easy_tdx"
    )
    return result.returncode, result.stdout, result.stderr

def main():
    print("=" * 60)
    print("easy_tdx 项目状态检查")
    print("=" * 60)
    
    # 1. 检查 Python 环境
    print("\n[1] 检查 Python 环境...")
    rc, out, err = run_cmd("python --version")
    print(f"  Python: {out.strip()}")
    
    # 2. 检查虚拟环境
    print("\n[2] 检查虚拟环境...")
    venv_python = "/home/skp/workspace/easy_tdx/.venv/bin/python"
    if os.path.exists(venv_python):
        rc, out, err = run_cmd(f"{venv_python} --version")
        print(f"  venv Python: {out.strip()}")
    else:
        print("  虚拟环境不存在")
    
    # 3. 运行 chanlun 几何测试
    print("\n[3] 运行缠论几何正确性测试...")
    rc, out, err = run_cmd(f"{venv_python} -m pytest tests/unit/test_chanlun_geometry.py -v --tb=short")
    print(out[-2000:] if len(out) > 2000 else out)
    if err:
        print(f"  ERR: {err[-500:]}")
    
    # 4. 运行缠论相关测试
    print("\n[4] 运行缠论相关单元测试...")
    rc, out, err = run_cmd(f"{venv_python} -m pytest tests/unit/test_chanlun*.py -v --tb=short -q")
    print(out[-2000:] if len(out) > 2000 else out)
    
    # 5. 运行信号准确度测试
    print("\n[5] 运行信号准确度测试...")
    rc, out, err = run_cmd(f"{venv_python} -m pytest tests/unit/test_backtest_signal_accuracy*.py -v --tb=short -q")
    print(out[-1500:] if len(out) > 1500 else out)
    
    # 6. 运行全量测试统计
    print("\n[6] 运行全量单元测试统计...")
    rc, out, err = run_cmd(f"{venv_python} -m pytest tests/unit/ -q --tb=no")
    # 提取通过/失败统计
    for line in out.split('\n'):
        if 'passed' in line or 'failed' in line or 'error' in line:
            print(f"  {line.strip()}")
    
    # 7. 检查 mypy
    print("\n[7] 运行 mypy 类型检查...")
    rc, out, err = run_cmd(f"{venv_python} -m mypy src/easy_tdx/chanlun/ --ignore-missing-imports")
    errors = [l for l in out.split('\n') if 'error' in l.lower()]
    if errors:
        print(f"  发现 {len(errors)} 个类型错误:")
        for e in errors[:10]:
            print(f"    {e}")
    else:
        print("  类型检查通过")
    
    # 8. 检查 ruff
    print("\n[8] 运行 ruff lint...")
    rc, out, err = run_cmd(f"{venv_python} -m ruff check src/easy_tdx/chanlun/")
    if out.strip():
        print(f"  发现 lint 问题:\n{out}")
    else:
        print("  lint 检查通过")
    
    print("\n" + "=" * 60)
    print("检查完成")
    print("=" * 60)

if __name__ == "__main__":
    main()
