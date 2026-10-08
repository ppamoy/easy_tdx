#!/usr/bin/env python3
"""⚠️ 未推送提交的**兜底检查**（2026-10-08，因一次真实事故而加）。

## 为什么有这个脚本
本轮我在探针分支上跑了 `git reset --hard ppamoy/main`，
结果 `main` 被指到远端那个提交上，我在本轮做的 **8 个未推送提交
从分支上消失**。虽然对象还在 `.git` 里（靠 reflog 全救回来了），
但只要中间有一次 `git gc --prune`，它们就**永久没了**。

根因：**未推送的提交只靠分支指针维系**。
指针一动，内容就"失联"，而 `git status` 干干净净、看不出任何异常。

## 本脚本做什么
用 `git rev-list <branch> --not --remotes=<r>` 找出
「本地分支有、任何远端都没有」的提交。

⚠️⚠️ **不能用 `git fetch --dry-run <remote> <branch>` 判存在性**——
它只在**远端分支不存在**时才报错；远端分支**落后于**本地时照样成功返回
⇒ 第一版就栽在这里：守门恒返回"安全"，属**无牙齿守门**（AGENTS.md §7）。
2026-10-08 实测：`fetch --dry-run ppamoy main` 返回 0，
但当时 main 明明领先远端 8 个未推送提交。

若存在未推送提交，再检查有没有 tag / 备份分支兜底；没有就 exit 1。

## 用法
    scripts/check_unpushed_guard.py
    scripts/check_unpushed_guard.py --quiet

退出码：0 = 安全（有兜底或无未推送提交）；1 = 有未推送且无兜底。
"""

from __future__ import annotations

import argparse
import subprocess
import sys


def _git(*args: str) -> str:
    r = subprocess.run(["git", *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} 失败: {r.stderr.strip()}")
    return r.stdout.strip()


def unpushed() -> dict[str, list[str]]:
    """返回 {本地分支: [未推送的 commit sha, ...]}。"""
    remotes = _git("remote").split()
    brs = _git("for-each-ref", "--format=%(refname:short)", "refs/heads").split()
    if not remotes:
        # 没有远端 ⇒ 所有本地提交都算未推送
        return {b: _git("rev-list", b).splitlines() for b in brs}

    out: dict[str, list[str]] = {}
    for br in brs:
        # ⚠️ --not --remotes=<r>：把"任一远端已有"的提交排除掉
        # ⚠️ **不要**加 --max-count：会截断到上限，让人以为只有 200 个
        #    而实际有 1066 个 ⇒ 报告的数字本身就是错的。
        shas = _git("rev-list", br, *(f"--not", *(f"--remotes={r}" for r in remotes))).splitlines()
        if shas:
            out[br] = shas
    return out


def has_guard() -> tuple[bool, str]:
    """未推送提交是否有 tag / 备份分支兜底。"""
    tags = _git("tag", "-l", "backup/*").split()
    if tags:
        return True, f"tag {tags[0]}"
    brs = [
        b for b in _git("for-each-ref", "--format=%(refname:short)", "refs/heads").split()
        if b.startswith("backup/") or b.startswith("mirror/")
    ]
    if brs:
        return True, f"分支 {brs[0]}"
    return False, ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()

    pending = unpushed()
    if not pending:
        return 0

    total = sum(len(v) for v in pending.values())
    ok, what = has_guard()
    if ok:
        if not a.quiet:
            print(f"✅ {total} 个未推送提交有兜底：{what}")
        return 0

    print(f"❌ 有 {total} 个未推送提交，且**没有任何 tag / 备份分支兜底**！")
    for br, shas in pending.items():
        try:
            subj = _git("log", "-1", "--format=%s", shas[0])
        except RuntimeError:
            subj = ""
        print(f"   分支 {br}: {len(shas)} 个，最新 {shas[0][:8]} {subj}")
    print()
    print("   危险：`git reset --hard` / `checkout -B` 会让它们从分支上消失，")
    print("   而 `git status` 不会显示任何异常。")
    print()
    first = next(iter(pending))
    print("   先打兜底标签再做任何改写历史的操作：")
    print(f"     git tag backup/$(date +%Y%m%d-%H%M) {first}")
    return 1


if __name__ == "__main__":
    sys.exit(main())