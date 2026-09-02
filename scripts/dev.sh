#!/usr/bin/env bash
# easy_tdx 开发环境启动脚本
# 用法: bash scripts/dev.sh [backend|frontend|all]

set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

BACKEND_PORT=8000
FRONTEND_PORT=3012

start_backend() {
    echo "=== 启动后端服务 (port $BACKEND_PORT) ==="
    source .venv/bin/activate 2>/dev/null || true
    python -m uvicorn easy_tdx.cli.cmd_web:create_app --factory \
        --host 0.0.0.0 --port "$BACKEND_PORT" \
        --reload 2>&1 &
    BACKEND_PID=$!
    echo "后端 PID: $BACKEND_PID"
}

start_frontend() {
    echo "=== 启动前端开发服务器 (port $FRONTEND_PORT) ==="
    cd web-ui
    npm install 2>/dev/null || true
    npx vite --host 0.0.0.0 --port "$FRONTEND_PORT" 2>&1 &
    FRONTEND_PID=$!
    echo "前端 PID: $FRONTEND_PID"
    cd ..
}

run_tests() {
    echo "=== 运行单元测试 ==="
    source .venv/bin/activate 2>/dev/null || true
    python -m pytest tests/unit/test_chanlun.py tests/unit/test_chanlun_v84_train_session.py \
        tests/unit/test_chanlun_v83_changying_season.py -x --tb=short 2>&1
}

run_verify() {
    echo "=== 运行缠论模型验证 ==="
    source .venv/bin/activate 2>/dev/null || true
    python scripts/verify_chanlun_model.py
}

stop_all() {
    echo "=== 停止所有服务 ==="
    kill $(lsof -ti:$BACKEND_PORT) 2>/dev/null || true
    kill $(lsof -ti:$FRONTEND_PORT) 2>/dev/null || true
    echo "已停止"
}

case "${1:-all}" in
    backend)
        start_backend
        echo "后端已在后台启动，访问 http://localhost:$BACKEND_PORT/docs"
        ;;
    frontend)
        start_frontend
        echo "前端已在后台启动，访问 http://localhost:$FRONTEND_PORT"
        ;;
    all)
        start_backend
        start_frontend
        echo ""
        echo "=========================================="
        echo "  easy_tdx 开发环境已启动"
        echo "  后端: http://localhost:$BACKEND_PORT"
        echo "  前端: http://localhost:$FRONTEND_PORT"
        echo "  API文档: http://localhost:$BACKEND_PORT/docs"
        echo "  缠论分析: http://localhost:$FRONTEND_PORT/chanlun"
        echo "  回测页面: http://localhost:$FRONTEND_PORT/"
        echo "=========================================="
        echo ""
        echo "按 Ctrl+C 停止所有服务"
        wait
        ;;
    test)
        run_tests
        ;;
    verify)
        run_verify
        ;;
    stop)
        stop_all
        ;;
    *)
        echo "用法: $0 [backend|frontend|all|test|verify|stop]"
        exit 1
        ;;
esac
