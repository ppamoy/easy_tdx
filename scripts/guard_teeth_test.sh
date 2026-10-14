#!/usr/bin/env bash
# 守卫豁免的牙齿测试（AGENTS.md §7：一个从不会变红的门禁等于没有门禁）
#
# 判据=**端口存活**。--kill-stalled 是 killpg（按进程组杀），豁免一旦失效，
# dev 后端/reloader/Vite 会整组消失 ⇒ 8001、3012 必然不再 LISTEN。
# 端口没了就是被杀了，没有中间态，不会误判。
set -uo pipefail
cd /home/skp/workspace/easy_tdx

p8001() { ss -ltn 2>/dev/null | awk '{print $4}' | grep -cE ":8001$"; }
p3012() { ss -ltn 2>/dev/null | awk '{print $4}' | grep -cE ":3012$"; }

before=$(($(p8001) + $(p3012)))
echo "运行前 dev 端口存活数: $before (期望 2)"

.venv/bin/python scripts/guard_bg_jobs.py --kill-stalled --min-age-min 0 --sample 3 \
    >/tmp/guard_teeth_run.log 2>&1
after=$(($(p8001) + $(p3012)))
echo "运行后 dev 端口存活数: $after (期望 2)"
echo "--- 守卫输出 ---"
cat /tmp/guard_teeth_run.log
echo "--- 判定 ---"
if [ "$before" -eq 2 ] && [ "$after" -eq 2 ]; then
    echo "✅ PASS：常驻服务未被误杀"; exit 0
fi
echo "❌ FAIL：dev 服务被误杀（豁免失效）before=$before after=$after"; exit 1
