#!/usr/bin/env bash
# easy_tdx 开发环境启动脚本
#
# ⚠️ 端口职责（别串台）：
#   8000 = 用户 user systemd 服务 easy-tdx.service（Restart=always），
#          托管构建产物 web-ui/dist → **生产**，开发别碰
#   8001 = scripts/dev_backend.sh 的 dev 后端（--reload）→ **开发**
#   3012 = web-ui 的 Vite dev（HMR，/api 代理到 8001）→ **开发前端**
#
# 用法: bash scripts/dev.sh [backend|frontend|all|stop|test|verify]

set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

BACKEND_PORT=8000     # 生产（systemd 占用）—— 本脚本只读不用它起服务
FRONTEND_PORT=3012
# dev 后端端口（与 web-ui/vite.config.ts 的 VITE_API_PORT 默认值保持一致）
DEV_BACKEND_PORT="${DEV_BACKEND_PORT:-8001}"

port_busy() {
    ss -ltn 2>/dev/null | grep -q ":$1 "
}

pid_on_port() {
    ss -ltnp 2>/dev/null | grep ":$1 " | grep -oE "pid=[0-9]+" | cut -d= -f2 | sort -u
}

start_backend() {
    # ⚠️ 开发后端**不能**起在 8000：那是生产 systemd 服务（Restart=always），
    #    叠进程必抢端口。实测 2026-10-10：
    #      ERROR: [Errno 98] address already in use
    #    且生产的 EASY_TDX_WEB_DIST=web-ui/dist 托管的是**构建产物**，
    #    改了 .vue 只看 8000 永远看不到变化。
    #    本函数改为委托 scripts/dev_backend.sh 起 8001（--reload）。
    if port_busy "$DEV_BACKEND_PORT"; then
        echo "=== dev 后端已在 port $DEV_BACKEND_PORT 运行，跳过 ==="
        for p in $(pid_on_port "$DEV_BACKEND_PORT"); do echo "    pid=$p"; done
        return 0
    fi
    echo "=== 启动 dev 后端 (port $DEV_BACKEND_PORT, --reload) ==="
    bash "$PROJECT_DIR/scripts/dev_backend.sh" --detach
}

start_frontend() {
    if port_busy "$FRONTEND_PORT"; then
        echo "=== 前端 dev server 已在 port $FRONTEND_PORT 运行，跳过 ==="
        return 0
    fi
    echo "=== 启动前端 dev server (port $FRONTEND_PORT) ==="
    # ⚠️ 原本这里写的是 npm 不存在的一次性参数，属于写错；且每次起服务都
    #    重装依赖没必要（slow + 可能冲掉 lockfile）。只在缺 node_modules 时装。
    if [ -d web-ui/node_modules ]; then
        echo "    node_modules 已存在，跳过安装"
    else
        (cd web-ui && npm install) || true
    fi
    (
        cd web-ui
        nohup npx vite --host 0.0.0.0 --port "$FRONTEND_PORT" \
            >> "$PROJECT_DIR/logs/dev-frontend.log" 2>&1 &
        echo "前端 PID: $!"
    )
}

run_tests() {
    echo "=== 运行单元测试 ==="
    .venv/bin/python -m pytest tests/unit/test_chanlun.py tests/unit/test_chanlun_v84_train_session.py \
        tests/unit/test_chanlun_v83_changying_season.py -x --tb=short 2>&1
}

run_verify() {
    echo "=== 运行缠论模型验证 ==="
    .venv/bin/python scripts/verify_chanlun_model.py
}

stop_all() {
    echo "=== 停止 dev 服务（$DEV_BACKEND_PORT / $FRONTEND_PORT）==="
    # ⚠️ 不要 kill 8000：那是 systemd 生产服务，杀了会被 Restart=always 自动拉起。
    for port in "$DEV_BACKEND_PORT" "$FRONTEND_PORT"; do
        for p in $(pid_on_port "$port"); do
            echo "kill pid=$p (port $port)"
            kill -9 "$p" 2>/dev/null || true
        done
    done
    echo "已停止"
}

case "${1:-all}" in
    backend)
        start_backend
        echo "dev 后端: http://localhost:$DEV_BACKEND_PORT  (docs: /docs)"
        ;;
    frontend)
        start_frontend
        echo "前端: http://localhost:$FRONTEND_PORT"
        ;;
    all)
        start_backend
        start_frontend
        echo ""
        echo "=========================================="
        echo "  easy_tdx 开发环境已启动"
        echo "  dev 后端:  http://localhost:$DEV_BACKEND_PORT  (docs: /docs)"
        echo "  前端 dev:  http://localhost:$FRONTEND_PORT"
        echo "  缠论分析:  http://localhost:$FRONTEND_PORT/learn?tab=analysis"
        echo "  回测页面:  http://localhost:$FRONTEND_PORT/"
        echo "  停止:      bash scripts/dev.sh stop"
        echo "------------------------------------------"
        echo "  生产服务 http://localhost:$BACKEND_PORT 未被本脚本改动"
        echo "=========================================="
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
