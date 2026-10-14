"""板块优先排序：按行业板块强度对个股排序加权。

缠论选股在多标的同时，自然应优先选择处于强势板块的标的——
板块涨跌幅代表资金整体流向，强势板块内的信号胜率更高。

实现：
1. 从 MAC 客户端取行业板块排行（HY），按涨跌幅排序。
2. 取前 N 个最强板块的成分股，建立 stock → (sector_name, sector_rank) 映射。
3. 对扫描结果列表，按 sector_rank + signal_score 综合排序。

无 MAC 客户端或取数失败时静默降级为原序（不阻断流程）。
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# 取前 N 个最强行业板块的成分股（控制 API 调用量）
_TOP_SECTORS = 5


def fetch_sector_ranking(top_n: int = _TOP_SECTORS) -> dict[str, tuple[str, int]] | None:
    """取行业板块排行，返回 stock_code → (sector_name, sector_rank) 映射。

    sector_rank=1 是最强板块，数值越小越优先。
    只映射前 ``top_n`` 个板块的成分股。

    失败返回 None（调用方降级为原序）。
    """
    try:
        from easy_tdx.cli.conn import get_mac_client
        from easy_tdx.mac.parsers import BoardType
    except Exception:
        return None

    try:
        with get_mac_client() as client:
            # 1. 取全部行业板块（含涨跌幅）
            boards = client.get_board_ranking(
                board_type=BoardType.HY,
                top_n=top_n,
                sort_by="change_pct",
                ascending=False,
            )
            if boards is None or boards.empty:
                logger.info("板块排行返回空，跳过板块优先排序")
                return None

            # 2. 对前 top_n 个板块取成分股
            mapping: dict[str, tuple[str, int]] = {}
            for rank, (_, board) in enumerate(boards.iterrows(), 1):
                board_code = str(board["code"])
                board_name = str(board.get("name", board_code))
                try:
                    members = client.get_board_members(board_code, count=500)
                except Exception:
                    continue
                if members is None or members.empty:
                    continue
                # 成分股 code 格式可能是 "SH600276" 或 "600276"
                for _, m in members.iterrows():
                    raw_code = str(m.get("code", ""))
                    # 统一为 6 位代码
                    code = raw_code.lstrip("SHszSZ").lstrip("0") if raw_code else ""
                    # 保留标准 6 位
                    if len(code) < 6:
                        code = raw_code[-6:] if len(raw_code) >= 6 else raw_code
                    if code and code not in mapping:
                        mapping[code] = (board_name, rank)

            logger.info("板块优先排序映射: %d 只 (前 %d 板块)", len(mapping), top_n)
            return mapping

    except Exception as exc:
        logger.warning("板块排行取数失败，降级为原序: %s", exc)
        return None


def apply_sector_priority(
    results: list[dict[str, Any]],
    sector_map: dict[str, tuple[str, int]] | None,
) -> list[dict[str, Any]]:
    """对扫描结果列表应用板块优先排序。

    排序逻辑：
    1. 有板块映射的标的按 sector_rank 升序（强板块优先）；
    2. 同板块内按 signal score 降序；
    3. 无板块映射的标的排到最后，按 score 降序。

    每个结果 dict 新增字段：
    - ``sector_name``: 所属行业名称（无则为 None）
    - ``sector_rank``: 板块排名（无则为 None）

    Args:
        results: 扫描结果列表，每个 dict 须有 ``code`` 字段。
        sector_map: :func:`fetch_sector_ranking` 的返回值，None 时原序返回。

    Returns:
        排序后的列表（新列表，不修改原列表）。
    """
    if not sector_map:
        return list(results)

    enriched: list[dict[str, Any]] = []
    for r in results:
        code = str(r.get("code", ""))
        info = sector_map.get(code)
        r2 = dict(r)
        if info:
            r2["sector_name"] = info[0]
            r2["sector_rank"] = info[1]
        else:
            r2["sector_name"] = None
            r2["sector_rank"] = None
        enriched.append(r2)

    # 有板块的在前，无板块在后
    enriched.sort(
        key=lambda r: (
            0 if r.get("sector_rank") is not None else 1,
            r.get("sector_rank") or 999,
            -(r.get("score", r.get("signal_score", 0)) or 0),
        )
    )
    return enriched


def enrich_results_with_sector(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """一站式：取板块排行 + 应用优先排序。供 scan_pool 直接调用。"""
    sector_map = fetch_sector_ranking()
    return apply_sector_priority(results, sector_map)
