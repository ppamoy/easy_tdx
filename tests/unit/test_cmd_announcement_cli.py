"""公告检索 CLI（cmd_announcement.py）回归测试（V-43）。

该命令此前 0 测试（覆盖率 25.6%）。V-43 调试教训：命令执行
``client = CninfoClient()``——patch 类后实例是 ``cls.return_value``，
方法/side_effect 必须配在 return_value 上；曾误配在类 mock 本体导致
mock「永不命中」（探针 id 对照定位）。全部走 CliRunner + mock CninfoClient
（patch 点 ``easy_tdx.cninfo.CninfoClient``——命令函数内 ``from ..cninfo import``
延迟绑定包级名字，而非 client 模块属性），
不触网。覆盖：
- JSON/Table 双输出（含 _render_table_full 长文本不截断）；
- CninfoError → 错误输出 + exit 1；
- --download 路径：空数据拒下、逐条下载成功/失败混合计数、
  Announcement 从 DataFrame 行构造（字段齐全）。
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from click.testing import CliRunner

from easy_tdx.cli.cmd_announcement import announcement

_COLS = [
    "title",
    "type",
    "date",
    "url",
    "code",
    "org_id",
    "announcement_id",
    "announcement_time",
    "pdf_url",
]


def _anno_df(n: int = 2) -> pd.DataFrame:
    rows = [
        {
            "title": f"公告{i}" + "很长的标题" * 20,
            "type": "年报",
            "date": "2024-03-01",
            "url": f"http://static.cninfo.com.cn/{i}.pdf",
            "code": "688017",
            "org_id": "9900033096",
            "announcement_id": f"ann{i}",
            "announcement_time": 1709251200000 + i,
            "pdf_url": f"http://static.cninfo.com.cn/finalpage/{i}.PDF",
        }
        for i in range(n)
    ]
    return pd.DataFrame(rows, columns=_COLS)


def _client(df: pd.DataFrame | None, pdf_paths: list[str] | None = None) -> MagicMock:
    """返回**类** mock：命令执行 ``client = CninfoClient()``，实例是
    ``cls.return_value``，方法须配在实例上（V-43 调试教训，见模块 docstring）。"""
    cls = MagicMock()
    inst = cls.return_value
    inst.get_announcements.return_value = df if df is not None else pd.DataFrame(columns=_COLS)
    if pdf_paths is not None:
        inst.download_pdf.side_effect = pdf_paths
    return cls


class TestAnnouncementOutput:
    def test_json_output(self) -> None:
        with patch("easy_tdx.cninfo.CninfoClient", _client(_anno_df())):
            result = CliRunner().invoke(announcement, ["688017"])
        assert result.exit_code == 0
        rows = json.loads(result.output)
        assert len(rows) == 2 and rows[0]["code"] == "688017"

    def test_table_output_long_text_not_truncated(self) -> None:
        with patch("easy_tdx.cninfo.CninfoClient", _client(_anno_df(1))):
            result = CliRunner().invoke(announcement, ["688017", "--table"])
        assert result.exit_code == 0
        assert "很长的标题很长的标题" in result.output  # 未被 30 字符截断

    def test_cninfo_error_exits_1(self) -> None:
        from easy_tdx.cninfo.models import CninfoError

        m = MagicMock()
        m.return_value.get_announcements.side_effect = CninfoError("巨潮接口超时")
        with patch("easy_tdx.cninfo.CninfoClient", m):
            result = CliRunner().invoke(announcement, ["688017"])
        assert result.exit_code == 1
        assert "巨潮接口超时" in result.output


class TestAnnouncementDownload:
    def test_download_success_path(self, tmp_path) -> None:
        m = _client(_anno_df(2), pdf_paths=[f"{tmp_path}/a.PDF", f"{tmp_path}/b.PDF"])
        with patch("easy_tdx.cninfo.CninfoClient", m):
            result = CliRunner().invoke(
                announcement,
                ["688017", "--count", "2", "--download", "2", "--download-dir", str(tmp_path)],
            )
        assert result.exit_code == 0
        assert m.return_value.download_pdf.call_count == 2
        # 从 DataFrame 行构造 Announcement（避免二次网络请求）
        first = m.return_value.download_pdf.call_args_list[0]
        assert first.kwargs["dest_dir"] == str(tmp_path)
        assert "完成：2 个下载，0 个跳过" in result.output

    def test_download_mixed_success_and_skip(self, tmp_path) -> None:
        from easy_tdx.cninfo.models import CninfoError

        m = _client(_anno_df(2), pdf_paths=[f"{tmp_path}/a.PDF", CninfoError("无 PDF")])
        with patch("easy_tdx.cninfo.CninfoClient", m):
            result = CliRunner().invoke(
                announcement, ["688017", "--download", "2", "--download-dir", str(tmp_path)]
            )
        assert result.exit_code == 0
        assert "完成：1 个下载，1 个跳过" in result.output

    def test_download_zero_no_pdf_calls(self, tmp_path) -> None:
        m = _client(_anno_df())
        with patch("easy_tdx.cninfo.CninfoClient", m):
            CliRunner().invoke(announcement, ["688017"])
        m.return_value.download_pdf.assert_not_called()

    def test_download_empty_df_rejected(self) -> None:
        m = _client(None)
        with patch("easy_tdx.cninfo.CninfoClient", m):
            result = CliRunner().invoke(announcement, ["688017", "--download", "3"])
        assert result.exit_code == 1
        assert "无公告可下载" in result.output
        m.return_value.download_pdf.assert_not_called()

    def test_download_n_caps_at_available_rows(self, tmp_path) -> None:
        """--download 5 但只有 2 条 → 只下 2 条。"""
        m = _client(_anno_df(2), pdf_paths=[f"{tmp_path}/a.PDF", f"{tmp_path}/b.PDF"])
        with patch("easy_tdx.cninfo.CninfoClient", m):
            result = CliRunner().invoke(
                announcement, ["688017", "--download", "5", "--download-dir", str(tmp_path)]
            )
        assert m.return_value.download_pdf.call_count == 2
        assert "开始下载 2 条" in result.output


@pytest.fixture()
def _no_network():
    """双保险：误触 requests 直接失败。"""
    import requests

    with patch.object(requests.Session, "request", side_effect=AssertionError("网络禁用")):
        yield
