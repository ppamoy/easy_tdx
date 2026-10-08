#!/usr/bin/env bash
# 重建 verify_measured_bases.py 依赖的 13 份基线缓存，并放进 **audit_bases/**。
#
# ⚠️ 为什么要固化这个脚本（2026-10-08）：
#   这 13 份缓存原本散落在 /tmp/ 下，而 /tmp 会被系统清理。
#   一清掉，漂移闸门就只能报"缺 13 份缓存"，
#   它给的建议（重跑审计脚本）等于让人重跑几小时 —— 而没人知道要跑哪 13 条。
#
# 用法：
#   scripts/regen_measured_bases.sh            # 全量（286 只，慢）
#   scripts/regen_measured_bases.sh --quick    # 快速冒烟（12 只，仅验证流程通不通）
#
# ⚠️ 并行度：走 _concurrency 的 DEFAULT_WORKERS(2)。
#    本机只有 4 核，硬编码 workers=4/8 会和 web 服务、pytest 正面抢核
#    （见 docs/BG_JOB_SLowness_POSTMORTEM.md）。
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

LIMIT=286
LIMIT_120=120
if [[ "${1:-}" == "--quick" ]]; then
  LIMIT=12
  LIMIT_120=12
fi

OUT_DIR="audit_bases"
mkdir -p "$OUT_DIR"

PY=".venv/bin/python"
if [[ ! -x "$PY" ]]; then
  echo "❌ 找不到 $PY" >&2
  exit 2
fi

# ⚠️ 口径 -> 审计脚本参数。**顺序与 verify_measured_bases.BASES 的文件名严格对应**，
#    改一边必须改另一边（那边有测试锁 BASES 必须经 _cache() 解析）。
#    格式：<输出文件名>|<传给 audit 的参数...>
run_one() {
  local out_name="$1"; shift
  # ⚠️⚠️ **逐口径**决定样本量，别想当然全用 $LIMIT：
  #    verify_measured_bases.py 里的 u120_*/sig_* 口径是**120 只**口径
  #    （登记数字就是按 120 只算出来的），而 full_inside/mq_* 是 **286 只**。
  #    若用 286 去重算 u120_*，登记的 t/p 就对不上了 ⇒ 闸门会误报漂移。
  local limit="$LIMIT"
  case "$out_name" in
    u120_*|sig_*) limit="${LIMIT_120:-120}" ;;
  esac
  local raw="/tmp/rb_${out_name%.json}"
  echo "=== $out_name ==="
  # 先落到 /tmp（脚本会自己给缓存名加口径 tag），再搬到 audit_bases/
  $PY scripts/audit_chanlun_screen_usefulness.py \
      --limit "$limit" --cache "$raw" "$@" >/dev/null 2>&1
  local produced
  produced=$(ls -t /tmp/"$(basename "${raw%.json}")"_*.json 2>/dev/null | head -1)
  if [[ -z "$produced" || ! -s "$produced" ]]; then
    echo "   ❌ 没产出缓存：$out_name" >&2
    return 1
  fi
  # ⚠️ 必须校验条数，空/残缺缓存比没有缓存更危险（闸门会拿它算出假结论）
  local n
  n=$($PY -c "import json,sys;print(len(json.load(open(sys.argv[1],encoding='utf-8'))))" "$produced" 2>/dev/null || echo 0)
  if [[ "$n" -lt 1 ]]; then
    echo "   ❌ 缓存为空（0 条）：$out_name" >&2
    return 1
  fi
  cp "$produced" "$OUT_DIR/$out_name"
  echo "   ✅ $n 条 → $OUT_DIR/$out_name"
}

FAILED=0
run_one u120_base_any_buy_any_any_false.json   --has-beichi false || FAILED=1
run_one u120_above_any_buy_any_above_false.json --zs-position above --has-beichi false || FAILED=1
run_one u120_tup_any_buy_up_any_false.json      --trend up --has-beichi false || FAILED=1
run_one u120_tdown_any_buy_down_any_false.json  --trend down --has-beichi false || FAILED=1
run_one u120_bc_any_buy_any_any_true.json      --has-beichi true || FAILED=1
run_one u120_below_any_buy_any_below_false.json --zs-position below --has-beichi false || FAILED=1
run_one sig_1buy_1buy_any_any_any.json         --signal-type 1buy || FAILED=1
run_one sig_2buy_2buy_any_any_any.json         --signal-type 2buy || FAILED=1
run_one sig_3buy_3buy_any_any_any.json         --signal-type 3buy || FAILED=1
run_one sig_1sell_1sell_any_any_any.json       --signal-type 1sell || FAILED=1
run_one full_inside_any_buy_any_inside_false.json --zs-position inside --has-beichi false || FAILED=1
run_one mq_q80_any_buy_any_any_any.json        --min-quality 80 || FAILED=1
run_one mq_zs5_any_buy_any_any_any.json        --min-zs-count 5 || FAILED=1

echo "-------------------------------------------"
if [[ "$FAILED" -ne 0 ]]; then
  echo "❌ 有口径没产出缓存（见上），不要把残缺的基线当结论用" >&2
  exit 1
fi
echo "✅ 13 份基线已重建到 $OUT_DIR/"
echo "   现在跑： $PY scripts/verify_measured_bases.py"