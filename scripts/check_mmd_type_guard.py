"""买卖点类型判定的守门脚本（防止 `endswith("buy")` 漏判 `2buy_s` 复发）。

为什么需要这个脚本：
    `2buy_s`（类二买）**不以 "buy" 结尾**（以 `_s` 结尾），所以用
    `t.endswith("buy")` 判买卖方向会得到 False ⇒ 被当成**卖点取反**
    ⇒ 产出**稳定且显著的错误结论**（实测：三档 t = −7.10 / −3.99 / −5.80，
    全是假的反向信号）。

    这个坑本项目**踩了两次**：
      1. V733_AUDIT_REPORT.md 五之九（文档里明确警告过）
      2. scripts/verify_chanlun_correctness.py（新脚本，又踩一次）

    文档警告没拦住复发 —— 因为它是散落的文字，不是可执行断言。
    所以这里做**源码扫描**：任何生产代码里出现该类判定，一律报错。

用法：
    python3 scripts/check_mmd_type_guard.py        # 检查
    exit 0 = 干净；exit 1 = 发现可疑判定
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# 生产代码目录（不含测试、文档、缓存）
SCAN_DIRS = ["src", "scripts", "web-ui/src"]

# 可疑模式：用 endswith/startswith 判买卖方向
BAD_PATTERNS = [
    (re.compile(r"""\.endswith\(\s*['"]buy['"]"""), 'endswith("buy")'),
    (re.compile(r"""\.endswith\(\s*['"]sell['"]"""), 'endswith("sell")'),
]

# 只扫 .py（.vue 里的模板/脚本混排，误报太多，交给 vitest 守）
SUFFIXES = (".py",)

# 允许出现的地方：
#   - 纯注释行 / docstring 行（文档里讲这个坑是好事）
#   - 本守门脚本自身（它必须引用坏写法才能描述它）
DOC_ONLY = re.compile(r"^\s*(#|\*|//)")
GUARD_SELF = "check_mmd_type_guard.py"


def main() -> int:
    hits: list[tuple[str, int, str, str]] = []
    for d in SCAN_DIRS:
        base = ROOT / d
        if not base.exists():
            continue
        for f in base.rglob("*.py"):
            if "__pycache__" in str(f) or f.name == GUARD_SELF:
                continue
            try:
                lines = f.read_text(encoding="utf-8").splitlines()
            except Exception:  # noqa: BLE001
                continue
            in_docstring = False
            for i, ln in enumerate(lines, 1):
                stripped = ln.strip()
                # 粗略跟踪三引号 docstring —— 里面讲这个坑是**好事**，不算违规
                if stripped.count('\"\"\"') % 2 == 1:
                    in_docstring = not in_docstring
                    if DOC_ONLY.match(ln):
                        continue
                if in_docstring:
                    continue
                for pat, name in BAD_PATTERNS:
                    if pat.search(ln) and not DOC_ONLY.match(ln):
                        hits.append((str(f.relative_to(ROOT)), i, name, ln.strip()))

    if not hits:
        print("✅ 未发现 endswith/startswith 判买卖方向的可疑代码")
        return 0

    print(f"❌ 发现 {len(hits)} 处可疑的买卖点类型判定：")
    print()
    print("   ⚠️ `2buy_s`（类二买）不以 \"buy\" 结尾 ⇒ endswith 漏判 ⇒ 符号取反")
    print("   ✅ 正确口径：`\"buy\" in t`，或复用 signal_stats.is_buy_type()")
    print()
    for path, ln, name, src in hits:
        print(f"   {path}:{ln}  [{name}]")
        print(f"      {src}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
