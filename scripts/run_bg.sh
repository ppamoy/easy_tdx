#!/usr/bin/env bash
# 后台任务统一入口 —— 强制回收，杜绝"卡死后没人管"再次发生。
#
# 起因（2026-10-07 事故，详见 docs/BG_JOB_SLowness_POSTMORTEM.md）：
#   4 个 audit worker 卡死后没被回收，长期 100% 占核，
#   导致同一个 session 里每个后台任务都要等 40~100 分钟。
#
# 设计要点：
#   1) 强制超时：不留侥幸，到点必死
#   2) 同进程组：保证 SIGKILL 能连 worker 一起带走，不留孤儿
#   3) 退出即回收：trap EXIT 兜底，脚本被杀也不会漏
#
# 用法：
#   scripts/run_bg.sh [--force] <超时秒数> <任务名> <命令...>
#
# 例：
#   scripts/run_bg.sh 1800 screen-usefulness \
#       .venv/bin/python scripts/audit_chanlun_screen_usefulness.py --limit 60
set -uo pipefail

# ⚠️ --force 必须**在任何 shift 之前**解析。
#    我第一版把它放在 TIMEOUT_S/NAME 已经 shift 掉之后，
#    ⇒ "--force" 被当成超时秒数（实测：任务=60 超时=--forces）
#    ⇒ 又一个"改了但没生效"的静默失效。
FORCE=0
if [[ "${1:-}" == "--force" ]]; then
  FORCE=1; shift
fi

if [[ $# -lt 3 ]]; then
  echo "用法: $0 [--force] <超时秒数> <任务名> <命令...>" >&2
  exit 2
fi

TIMEOUT_S="$1"; shift
NAME="$1"; shift

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/easy_tdx/bg_jobs"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/${NAME}.$(date +%Y%m%d_%H%M%S).log"

echo "[run_bg] 任务=$NAME 超时=${TIMEOUT_S}s 日志=$LOG" >&2

# ── 起飞前检查：别再叠加长任务 ────────────────────────────────────────
# ⚠️ 起因：本机只有 4 核，我**两次**把 CPU 占满（用户当面指出两回）。
#    第二次的叠加是：pytest 全量(约4800用例) + 基线审计(2 worker) +
#    前端 npm test，实测 328%/400%，还叠加了另一个 agent 的 e2e。
# ⇒ 守卫之前只**事后报警**，拦不住"我已经在跑了还再起一个"。
#    这里改成**起飞前**就挡。
#    ⚠️ --force 必须真的存在：上面这句"要强行走用 --force"是写给人看的，
#       不实现就是空头承诺（我刚犯过这类"注释说有、代码没有"的错）。
if [[ -x "$PROJECT_DIR/scripts/can_start_bg.py" ]]; then
  if ! "$PROJECT_DIR/.venv/bin/python" "$PROJECT_DIR/scripts/can_start_bg.py"; then
    if [[ "$FORCE" -eq 1 ]]; then
      echo "[run_bg] ⚠️ --force：忽略占位警告，照跑（占满 4 核自负）。" >&2
    else
      echo "[run_bg] ❌ 拒绝启动：已有长任务在跑（见上）。" >&2
      echo "[run_bg]    确认要叠就加 --force。" >&2
      exit 3
    fi
  fi
fi

# 整个子树放进同一个进程组：这样 pkill -P / 进程组信号能连带清理
# worker，不会出现"父死了 worker 还活着占核"的情况。
set -m

LOG_TMP="$LOG"
cleanup() {
  local rc=$?
  kill -TERM  -$$ 2>/dev/null || true
  sleep 2
  kill -KILL -$$ 2>/dev/null || true
  exit $rc
}
trap cleanup EXIT INT TERM

exec > >(tee "$LOG") 2>&1

echo "# started: $(date '+%Y-%m-%d %H:%M:%S')"
echo "# cmd    : $*"
echo "# timeout: ${TIMEOUT_S}s"
echo "-------------------------------------------"

# 注意：这里不能用 pipeline / command substitution 包裹，
# 否则 exit code 会被包裹层吞掉（之前 exit=3 被报成 0 就是这个原因）。
set +e
timeout -k 10 "${TIMEOUT_S}" "$@"
RC=$?
set -e

echo "-------------------------------------------"
if [[ $RC -eq 124 ]]; then
  echo "TIMEOUT: 达到 ${TIMEOUT_S}s 上限被强制终止"
fi
echo "exit=$RC at $(date '+%Y-%m-%d %H:%M:%S')"

exit $RC