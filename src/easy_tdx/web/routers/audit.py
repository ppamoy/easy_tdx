"""模型准确性审计路由（V722，R2）。

只读消费 audit/accuracy.py 落盘的报告；不在请求路径上跑审计
（全量审计要连服务器取数，属 CLI/调度职责）。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from easy_tdx.audit.accuracy import list_audit_history, load_latest_audit

router = APIRouter(tags=["audit"])


@router.get("/audit/accuracy")
async def audit_accuracy_latest(
    date: str | None = Query(None, description="报告日期 YYYY-MM-DD，缺省最新一份"),
) -> dict[str, Any]:
    """最新（或指定日期）审计报告：长盈分层前瞻 + 缠论信号质量 + 图表对账。"""
    if date:
        path = list_audit_history()
        hit = next((p for p in path if p["date"] == date), None)
        if hit is None:
            raise HTTPException(status_code=404, detail=f"无 {date} 的审计报告")
        import json
        from pathlib import Path

        report = json.loads(Path(hit["path"]).read_text(encoding="utf-8"))
    else:
        report = load_latest_audit()
    if report is None:
        raise HTTPException(
            status_code=404,
            detail="尚无审计报告，请先运行 easy-tdx audit-accuracy",
        )
    return report


@router.get("/audit/history")
async def audit_history() -> dict[str, Any]:
    """历史审计报告日期列表（供前端下拉切换）。"""
    return {"reports": list_audit_history()}
