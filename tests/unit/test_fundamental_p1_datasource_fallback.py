"""P1 数据源可用性实测（判定 docs/PRODUCT_REQUIREMENTS.md §8 的过时风险）。

需求文档 §8「待确认 / 风险」里写着：
    | gpcw 财报下载失败 | 文件列表可读，zip 下载 0 字节 | ... 失败则切换新浪 |

但 §4 能力清单（行 39）却标 ✅「zip 下载+解析正常」。两处自相矛盾。
本测试用**实测**判定谁对（AGENTS.md 纪律 3：先实测再下结论）：

1. gpcw：本地缓存 zip 真实存在且能解析出全市场记录（含披露日）；
2. 新浪回退：gpcw 全空时，能从新浪财报兜底并正确打上 data_source="sina"。

结论（本机实测）：gpcw 已打通、新浪回退已接通 ⇒ §8 那条风险**已解除**，
文档里「zip 下载 0 字节」属过时信息（已在文档中标注「已证伪」）。

注：gpcw 用例依赖 ~/.easy_tdx/gpcw_cache 的本地缓存（首次下载需联网）；
无缓存时跳过，不算失败 —— 但**新浪回退**用例不依赖网络（全 mock），
永远会跑，那才是「风险已解除」的持续保证。
"""

from __future__ import annotations

import glob
import os
from datetime import date
from unittest.mock import patch

import pandas as pd
import pytest

from easy_tdx.fundamental.indicators import build_indicator_frame, records_from_zip

TARGET = date(2025, 5, 1)


def _cache_dir() -> str:
    return os.path.expanduser("~/.easy_tdx/gpcw_cache")


@pytest.mark.skipif(
    not glob.glob(os.path.join(_cache_dir(), "*.zip")),
    reason="无 gpcw 本地缓存（需联网下载一次）",
)
class TestGpcwParsesRealData:
    """§8 声称「zip 下载 0 字节」—— 实测是否真的如此。"""

    def test_zip_parses_to_market_wide_records(self) -> None:
        fn = os.path.basename(sorted(glob.glob(os.path.join(_cache_dir(), "*.zip")))[-1])
        recs = records_from_zip(fn, client=None)
        assert len(recs) > 100, f"gpcw 解析记录数过少（{len(recs)}），疑似未打通"

    def test_disclosure_date_is_populated(self) -> None:
        """披露日是 point-in-time 的前提；缺了它 P1 就是空谈。"""
        fn = os.path.basename(sorted(glob.glob(os.path.join(_cache_dir(), "*.zip")))[-1])
        fr = build_indicator_frame(records_from_zip(fn, client=None))
        assert not fr.empty
        have = fr["disclosure_date"].notna().sum()
        assert have > 0, "披露日全为空，point-in-time 无法成立"
        # 覆盖率不应太低，否则大量股票会被保守排除
        assert have / len(fr) > 0.5, f"披露日覆盖率仅 {have}/{len(fr)}"


class TestSinaFallbackWhenGpcwUnavailable:
    """§8 的**应对方案**「切换新浪为数据源」是否真的接通（全 mock，不依赖网络）。"""

    def test_fallback_produces_sina_rows(self) -> None:
        import easy_tdx.fundamental.pipeline as P

        class R:
            code, market = "600519", "SH"
            report_date = date(2025, 3, 31)
            disclosure_date = date(2025, 4, 20)  # ≤ TARGET
            indicators = {
                "eps": 5.0, "roe": 25.0, "gross_margin": 60.0, "net_margin": 30.0,
                "rev_yoy": 12.0, "np_yoy": 15.0, "debt_ratio": 30.0,
                "net_profit": 2e9, "revenue": 4e10, "bps": 8.0,
            }

        with (
            patch.object(P, "load_all_periods_frame", return_value=pd.DataFrame()),
            patch.object(P, "pick_report_zips", return_value=[]),
            patch.object(P, "detect_season_for_date", return_value=None),
            patch(
                "easy_tdx.fundamental.sina_adapter.load_sina_rows",
                return_value=[R()],
            ),
        ):
            out = P.scan_market(
                TARGET,
                markets=["SH"],
                sina_pool=[{"market": "SH", "code": "600519"}],
                top_n=5,
            )

        results = out.get("results", [])
        assert results, "gpcw 不可用时新浪回退未生效 —— §8 应对方案没接通"
        assert results[0].get("data_source") == "sina", (
            f"应标注来自新浪，实得 {results[0].get('data_source')}"
        )

    def test_fallback_respects_point_in_time(self) -> None:
        """回退路径同样不得使用披露日 > target 的数据。"""
        import easy_tdx.fundamental.pipeline as P

        class Future:
            code, market = "600519", "SH"
            report_date = date(2025, 3, 31)
            disclosure_date = date(2026, 1, 1)  # > TARGET ⇒ 未来数据
            indicators = {"eps": 9.9, "roe": 25.0, "net_profit": 2e9, "revenue": 4e10}

        with (
            patch.object(P, "load_all_periods_frame", return_value=pd.DataFrame()),
            patch.object(P, "pick_report_zips", return_value=[]),
            patch.object(P, "detect_season_for_date", return_value=None),
            patch(
                "easy_tdx.fundamental.sina_adapter.load_sina_rows",
                return_value=[Future()],
            ),
        ):
            out = P.scan_market(
                TARGET,
                markets=["SH"],
                sina_pool=[{"market": "SH", "code": "600519"}],
                top_n=5,
            )
        assert out.get("results", []) == [], (
            "披露日在 target 之后的财报竟被选中 —— 回退路径有未来函数"
        )
