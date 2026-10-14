#!/bin/bash
# 每日自动刷新数据 + 全池扫描
#
# 用法（crontab）:
#   30 16 * * 1-5  cd /home/skp/workspace/easy_tdx && bash scripts/daily_scan.sh >> /tmp/daily_scan.log 2>&1
#
# 也支持手动运行:
#   bash scripts/daily_scan.sh
#
# 流程:
#   1. refresh_data.py — 刷新 K线+指数缓存（连 TDX）
#   2. scan_pool.py — 全池融合分析（读缓存，不连 TDX）
#   3. 输出报告到 audit_data/scan_result.json

set -euo pipefail
cd "$(dirname "$0")/.."

VENV=".venv/bin/python"
LOG="/tmp/daily_scan_$(date +%Y%m%d).log"

echo "===============================================" | tee "$LOG"
echo "  每日扫描 $(date '+%Y-%m-%d %H:%M:%S')" | tee -a "$LOG"
echo "===============================================" | tee -a "$LOG"

# ── 1. 刷新数据（失败不阻断扫描）──
echo "" | tee -a "$LOG"
echo "[1/2] 刷新 K线+指数数据..." | tee -a "$LOG"
if $VENV scripts/refresh_data.py 2>&1 | tee -a "$LOG"; then
    echo "  ✅ 数据刷新成功" | tee -a "$LOG"
else
    echo "  ⚠️ 数据刷新失败（用现有缓存继续扫描）" | tee -a "$LOG"
fi

# ── 2. 全池扫描 ──
echo "" | tee -a "$LOG"
echo "[2/2] 全池融合分析扫描..." | tee -a "$LOG"
$VENV scripts/scan_pool.py 2>&1 | tee -a "$LOG"

echo "" | tee -a "$LOG"
echo "===============================================" | tee -a "$LOG"
echo "  完成 $(date '+%Y-%m-%d %H:%M:%S')" | tee -a "$LOG"
echo "  报告: audit_data/scan_result.json" | tee -a "$LOG"
echo "  看板: http://127.0.0.1:8001/watchlist" | tee -a "$LOG"
echo "===============================================" | tee -a "$LOG"
