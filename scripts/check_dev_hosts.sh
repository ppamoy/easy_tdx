#!/usr/bin/env bash
# easy_tdx dev 域名白名单守门脚本
#
# 背景（2026-10-12 实测）：
#   cl.ppamoy.fun 打开是一片 403 "Blocked request. This host ("cl.ppamoy.fun")
#   is not allowed."。链路是：
#     浏览器 → NPM(docker: nginx-proxy-manager) proxy_host 60
#            → 192.168.1.201:3012（Vite dev server）
#   而 NPM 那条 conf **没有** header_up Host，Host 头原样透传给 Vite，
#   Vite 从 6.x 起有 DNS-rebinding 防护：server.allowedHosts 没列的域名一律 403。
#   → 每挂一个新的 ppamoy.fun 子域名到 3012，就会再炸一次。
#
# 本脚本干的事：**从反代配置反推**所有指向 dev 端口的域名，逐个真发请求，
# 断言 200（不是 403）。并带一个**对照组**：一个必然不在白名单的域名必须 403，
# 用来证明 Vite 真的在拦截（否则脚本会因为"全都通"而假 PASS）。
#
# 用法:
#   bash scripts/check_dev_hosts.sh            # 默认查 3012（web-ui dev）
#   bash scripts/check_dev_hosts.sh --port 3013  # 查别的端口（自测脚本本身用）
#
# 退出码: 0 = 通过；1 = 有域名被拦（或环境不对我认为的"通过"）；2 = 参数/环境错。

set -uo pipefail

VITE_PORT=3012
NPM_CONF_DIR="${NPM_CONF_DIR:-/mnt/docker/nginxproxymanager/npm_new_data/nginx/proxy_host}"
# 对照组域名：不可能出现在 allowedHosts 里。若它也被放行，说明 Vite 没真在拦。
CONTROL_HOST="__not_in_whitelist__.invalid"

while [ $# -gt 0 ]; do
    case "$1" in
        --port) VITE_PORT="${2:?--port 需要一个值}"; shift 2 ;;
        -h|--help) sed -n '2,25p' "$0"; exit 0 ;;
        *) echo "未知参数: $1（-h 看用法）" >&2; exit 2 ;;
    esac
done

echo "=== easy_tdx dev 域名白名单守门（Vite dev port $VITE_PORT）==="

# 0) dev server 活着吗？不活着必须报错退出，不能静默 skip（静默 skip = 假 PASS）。
if ! ss -ltn 2>/dev/null | grep -q ":$VITE_PORT "; then
    echo "FAIL: 端口 $VITE_PORT 没有在监听 —— Vite dev server 没起。"
    echo "      先起：bash scripts/dev.sh frontend"
    exit 1
fi

# 1) 从 NPM 反代配置里找出所有指向 $VITE_PORT 的域名
if [ ! -d "$NPM_CONF_DIR" ]; then
    echo "FAIL: NPM 反代配置目录不存在: $NPM_CONF_DIR"
    echo "      （不是 skip —— 找不到就是失败，别让守门变成摆设）"
    exit 1
fi

# 每个 conf 里 `set $port N;` + `server_name a b c;`；只有端口匹配的才收集。
# awk 逐段处理：以 server{} 块为单位，块内同时满足端口和 server_name 才输出。
mapfile -t HOSTS < <(
    awk -v wantport="$VITE_PORT" '
        /^ *server *\{/            { inblk=1; port=""; sn=""; next }
        inblk && /^ *\}/           { inblk=0;
                                     if (port == wantport && sn != "") {
                                       n = split(sn, a, /[ \t]+/);
                                       for (i=1; i<=n; i++) if (a[i] != "") print a[i];
                                     }
                                     next }
        inblk && /set \$port/      { gsub(/[^0-9]/, "", $0); port=$0; next }
        inblk && /server_name/     { sub(/^ *server_name */, ""); sub(/;.*$/, ""); sn=$0; next }
    ' "$NPM_CONF_DIR"/*.conf 2>/dev/null | sort -u
)

if [ ${#HOSTS[@]} -eq 0 ]; then
    echo "FAIL: 在 $NPM_CONF_DIR 里没找到任何指向 $VITE_PORT 的反代域名。"
    echo "      正常情况下至少应该有 easy.ppamoy.fun / cl.ppamoy.fun。"
    exit 1
fi

echo "反代配置里指向 $VITE_PORT 的域名：${HOSTS[*]}"
echo

# 2) 逐个真发请求（Host 头透传，模拟 NPM 的真实行为）
fail=0
for h in "${HOSTS[@]}"; do
    code=$(curl -s -o /dev/null -w '%{http_code}' \
             -H "Host: $h" "http://127.0.0.1:$VITE_PORT/" || echo 000)
    if [ "$code" = "200" ]; then
        echo "  OK   $h -> $code"
    else
        echo "  FAIL $h -> $code  ← 被 Vite 拦了(403)或 dev server 异常"
        echo "       修法：把 \"$h\" 加进 web-ui/vite.config.ts 的 server.allowedHosts"
        fail=1
    fi
done

# 3) 对照：白名单外的域名必须 403。若它被放行，说明上面的 200 是假的。
ctrl=$(curl -s -o /dev/null -w '%{http_code}' \
         -H "Host: $CONTROL_HOST" "http://127.0.0.1:$VITE_PORT/" || echo 000)
if [ "$ctrl" = "403" ]; then
    echo "  OK   对照组 $CONTROL_HOST -> 403（Vite 确实在拦非白名单域名）"
else
    echo "  FAIL 对照组 $CONTROL_HOST -> $ctrl，预期 403。"
    echo "       白名单可能被设成了 true / 通配过头，防护失效。"
    fail=1
fi

echo
if [ "$fail" -eq 0 ]; then
    echo "PASS: 所有反代域名都能进 dev server，且非白名单域名仍被拦。"
    exit 0
fi
echo "FAIL: 有域名被 dev server 拒了。"
exit 1
