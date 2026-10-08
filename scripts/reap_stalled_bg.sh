#!/usr/bin/env bash
# 后台任务僵尸自动清理 —— 用 cron 定期跑，无需 agent 在场。
#
# 起因：2026-10-07 发现 easy_tdx 的审计进程卡死后没被回收，
# 4 个 worker 长期占满 4 核，导致该 session 里"每个后台任务都非常久"。
#
# 用法（先 --dry-run 观察，确认无误再开自动清理）：
#   scripts/reap_stalled_bg.sh --dry-run
#   scripts/reap_stalled_bg.sh --auto
set -uo pipefail

PROJECT_DIR="${PROJECT_DIR:-/home/skp/workspace/easy_tdx}"
PY="$PROJECT_DIR/.venv/bin/python"
GUARD="$PROJECT_DIR/scripts/guard_bg_jobs.py"

MIN_AGE="${MIN_AGE:-15}"      # 存活至少多少分钟才允许清理（防误杀刚启动的）
SAMPLE="${SAMPLE:-15}"        # CPU 采样间隔秒

if [[ ! -x "$PY" ]]; then
  echo "[reap] 找不到解释器: $PY" >&2
  exit 127
fi

MODE="report"
if [[ "${1:-}" == "--auto" ]]; then
  MODE="kill"
elif [[ "${1:-}" == "--dry-run" ]]; then
  MODE="report"
elif [[ "${1:-}" != "" ]]; then
  echo "用法: $0 [--dry-run|--auto]" >&2
  exit 2
fi

ARGS=(--sample "$SAMPLE" --min-age-min "$MIN_AGE")
if [[ "$MODE" == "kill" ]]; then
  ARGS+=(--kill-stalled)
fi

LOG_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/easy_tdx"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/reap.log"

TS="$(date '+%Y-%m-%d %H:%M:%S')"
OUT="$("$PY" "$GUARD" "${ARGS[@]}" 2>&1)"
RC=$?

# 只在"动手了"或"发现问题"时记录，避免日志爆炸
if [[ "$MODE" == "kill" && $RC -ne 0 ]] || grep -q "已清理" <<<"$OUT"; then
  {
    echo "[$TS] rc=$RC mode=$MODE"
    echo "$OUT"
    echo "-------------------------------------------"
  } >> "$LOG"
fi

echo "$OUT"
exit $RC