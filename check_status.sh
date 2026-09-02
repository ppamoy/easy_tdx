#!/bin/bash
# 检查项目状态和运行测试

set -e

cd /home/skp/workspace/easy_tdx

echo "=== 检查 Python 环境 ==="
python --version
pip list | grep -E "pandas|numpy|fastapi|uvicorn|vue" || true

echo ""
echo "=== 检查虚拟环境 ==="
if [ -d ".venv" ]; then
    echo "虚拟环境存在"
    .venv/bin/python --version
else
    echo "虚拟环境不存在"
fi

echo ""
echo "=== 检查前端依赖 ==="
if [ -d "web-ui/node_modules" ]; then
    echo "前端依赖已安装"
else
    echo "前端依赖未安装"
fi

echo ""
echo "=== 运行单元测试（chanlun 相关）==="
.venv/bin/python -m pytest tests/unit/test_chanlun_geometry.py -v --tb=short 2>&1 | head -50

echo ""
echo "=== 运行全量单元测试（chanlun 部分）==="
.venv/bin/python -m pytest tests/unit/test_chanlun*.py -v --tb=short 2>&1 | tail -30

echo ""
echo "=== 检查 mypy 类型 ==="
.venv/bin/mypy src/easy_tdx/chanlun/ --ignore-missing-imports 2>&1 | tail -20

echo ""
echo "=== 检查 ruff lint ==="
.venv/bin/ruff check src/easy_tdx/chanlun/ 2>&1 | tail -10
