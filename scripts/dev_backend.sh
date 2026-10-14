#!/usr/bin/env bash
# easy_tdx **开发专用**后端（独立端口，绝不占用生产的 8000）
#
# 为什么单独一个脚本：
#   8000 已被用户的 user systemd 服务占用（~/.config/systemd/user/
#   easy-tdx.service，Restart=always，杀掉会被自动拉起）。开发再叠一个
#   进程上去会：① 端口冲突；② 生产的 EASY_TDX_WEB_DIST 指向 web-ui/dist
#   （构建产物），改了 .vue 源码看 8000 永远看不到变化。
#
# 本脚本起在 DEV_BACKEND_PORT（默认 8001），带 --reload，且显式
# EASY_TDX_WEB_DIST="" —— 避免误托管生产 dist。
#
# 用法:
#   bash scripts/dev_backend.sh            # 前台
#   bash scripts/dev_backend.sh --detach   # 后台（nohup，日志 logs/dev-backend.log）
#   bash scripts/dev_backend.sh --stop     # 停掉 dev 后端
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

DEV_BACKEND_PORT="${DEV_BACKEND_PORT:-8001}"
LOG="$PROJECT_DIR/logs/dev-backend.log"

stop_dev() {
    local pids
    pids=$(ss -ltnp 2>/dev/null | grep ":${DEV_BACKEND_PORT} " | grep -oE "pid=[0-9]+" | cut -d= -f2 | sort -u)
    if [ -z "$pids" ]; then
        echo "端口 $DEV_BACKEND_PORT 上没有 dev 后端在跑"
        return 0
    fi
    for p in $pids; do
        echo "停止 dev 后端 pid=$p"
        kill -9 "$p" 2>/dev/null || true
    done
    return 0
}

case "${1:-}" in
    --stop) stop_dev; exit 0 ;;
esac

# 端口自检：万一有人把 8001 也占了，别硬抢
if ss -ltn 2>/dev/null | grep -q ":${DEV_BACKEND_PORT} "; then
    echo "⚠️  端口 $DEV_BACKEND_PORT 已被占用，先停掉或换 DEV_BACKEND_PORT"
    ss -ltnp 2>/dev/null | grep ":${DEV_BACKEND_PORT} "
    exit 1
fi

mkdir -p "$PROJECT_DIR/logs"

# ⚠️ EASY_TDX_WEB_DIST 显式置空：dev 后端不托管生产 dist。
#    （生产服务在 8000 才指向 web-ui/dist，两者职责分离。）
#
# ⚠️ --reload-dir 限定监听范围为 src/ 和 web-ui/backend（如有）：
#    默认 uvicorn 监听整个工作目录（含 audit_*/、logs/、tmp/、tests/）。
#    实测 2026-10-10：跑脚本/写缓存时后端会自触发 reload，正在处理中的
#    请求被掐断 → 前端拿到 **502 Bad Gateway**（日志比对确认 reload 时间戳
#    与 502 时间重合，且 respond 时后端正在 Waiting for application startup）。
#    收窄监听范围既避免自重启，也省掉 WatchFiles 扫整个大目录的开销。
RELOAD_DIRS=()
for d in src web-ui/src; do
    [ -d "$PROJECT_DIR/$d" ] && RELOAD_DIRS+=(--reload-dir "$PROJECT_DIR/$d")
done

CMD=(.venv/bin/python -m uvicorn easy_tdx.web:create_app
     --factory --host 0.0.0.0 --port "$DEV_BACKEND_PORT" --reload
     "${RELOAD_DIRS[@]}")

if [ "${1:-}" = "--detach" ]; then
    nohup env EASY_TDX_WEB_DIST="" "${CMD[@]}" >> "$LOG" 2>&1 &
    echo "dev 后端已在后台启动 (port $DEV_BACKEND_PORT, --reload)"
    echo "日志: $LOG"
    for i in $(seq 1 40); do
        sleep 1
        if curl -s -o /dev/null "http://127.0.0.1:${DEV_BACKEND_PORT}/"; then
            echo "✅ 就绪: http://localhost:${DEV_BACKEND_PORT}  (docs: /docs)"
            exit 0
        fi
    done
    echo "⚠️  40s 内未就绪，看日志: $LOG"
else
    echo "dev 后端前台启动: http://localhost:${DEV_BACKEND_PORT}  (Ctrl+C 停止)"
    exec env EASY_TDX_WEB_DIST="" "${CMD[@]}"
fi
