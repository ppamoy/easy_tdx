"""P0 逐步揭示训练：**不得提前下发答案或未来走势**。

需求 F1（docs/PRODUCT_REQUIREMENTS.md §3.2）：
  「K 线从起点逐步推进……推进到潜在关键点时暂停并问『买/卖/观望』，
    我提交判断后，网站揭示缠论引擎在该位置的真实结论」

因此「答案」必须在**作答后才可见**。但实测（V731 审计）：
``POST /chanlun/train/session`` 一次性返回完整 payload，前端只用
``revealIndex`` 截断**图表渲染**，数据本身未截断：

  1. ``candidates[]`` 里真实信号点直接带 ``signal`` = {type, confidence,
     grade, explanation} —— 即**每题的正确答案**；
  2. ``mmd_outcomes[]`` 带信号后 5/10/20 日实际涨跌幅 —— **未来走势**；
  3. ``mmds[]`` 全量下发，含尚未揭示到的信号。

后果：用户 F12 打开 Network 面板即可读到全部答案与后续 20 日涨跌，
「逐步揭示训练」失去意义（实测 000333 日线：开局即可知 46/87/110 三个
答案点，以及 1buy 后 20 日 +13.17%）。

而 ``mmd_outcomes`` 其实是 **F2 复盘模式**才需要的（"事后验证"）。
前端虽有 train/review 两种模式，却共用同一接口与同一份 payload。

修复：``build_train_session_payload`` 新增 ``reveal_limit`` 参数。
  - ``None``（默认）= 复盘模式，保持原样（需要未来收益做事后验证）
  - 整数 N    = 训练模式，只下发 index <= N 的信息，答案与未来收益
                一律不下发（作答后由前端/后续请求再取）
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from fastapi.testclient import TestClient

from easy_tdx.chanlun.analyser import ChanlunAnalyser
from easy_tdx.chanlun.config import ChanlunConfig
from easy_tdx.web.routers.chanlun import build_train_session_payload

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
FIXTURE = "chanlun_000333_daily.json"


def _payload(reveal_limit=None):
    rows = json.loads((FIXTURES / FIXTURE).read_text(encoding="utf-8"))
    df = pd.DataFrame(rows)
    res = ChanlunAnalyser(code="T", frequency="daily", config=ChanlunConfig(zs_from_xd=False)).process_klines(df)
    if reveal_limit is None:
        return build_train_session_payload(res, df, "train")
    return build_train_session_payload(res, df, "train", reveal_limit=reveal_limit)


class TestReviewModeKeepsOutcomes:
    """对照组：复盘模式（reveal_limit=None）必须保持原样。"""

    def test_outcomes_present(self) -> None:
        p = _payload(None)
        assert p["mmd_outcomes"], "复盘模式需要 mmd_outcomes 做事后验证"
        assert any(o["ret_5d"] is not None for o in p["mmd_outcomes"])

    def test_candidates_carry_answers(self) -> None:
        p = _payload(None)
        assert [c for c in p["candidates"] if c["signal"]], "复盘模式应带答案"


class TestTrainModeHidesFuture:
    """训练模式：不得下发答案与未来走势。"""

    def test_no_outcomes_when_training(self) -> None:
        """训练模式下 mmd_outcomes 必须为空 —— 那是未来走势。"""
        p = _payload(10)
        assert p["mmd_outcomes"] == [], f"训练模式不应下发未来收益，实得 {p['mmd_outcomes']}"

    def test_no_answer_before_reveal(self) -> None:
        """尚未揭示到的信号点，其 signal 答案不得下发。"""
        p = _payload(10)
        for c in p["candidates"]:
            if c["index"] > 10:
                assert c["signal"] is None, (
                    f"候选点 {c['index']} 尚未揭示（limit=10）却带答案 {c['signal']}"
                )

    def test_past_candidates_still_available(self) -> None:
        """已揭示过的点应保留信息（不能矫枉过正把题目也删了）。"""
        p = _payload(200)  # 揭示到末尾
        assert p["candidates"], "已揭示的候选点不应被清空"

    def test_at_start_nothing_leaked(self) -> None:
        """开局（reveal_limit=0）时，不应有任何答案可见。"""
        p = _payload(0)
        leaked = [c for c in p["candidates"] if c["signal"] is not None]
        assert leaked == [], f"开局即泄漏答案：{leaked}"
        assert p["mmd_outcomes"] == []


class TestHttpEndpointGate:
    """真链路：HTTP 打到 /chanlun/train/session，验证防作弊闸门真的接通。

    只测纯函数是不够的 —— 闸门参数若没在路由里接通，单测照样过而线上
    照旧泄题（AGENTS.md 案例 A 的教训：UI 开关亮了但请求没带上）。
    """

    @staticmethod
    def _client() -> TestClient:
        from easy_tdx.web.app import _create_app

        return TestClient(_create_app())

    @staticmethod
    def _df() -> pd.DataFrame:
        rows = json.loads((FIXTURES / FIXTURE).read_text(encoding="utf-8"))
        return pd.DataFrame(rows)

    def _post(self, **extra):
        """extra 走 **query**（FastAPI 中 POST 的标量参数默认不是 body）。

        实测：mode/reveal_limit 放 body 时后端收不到（outcomes=0），
        放 query 才生效（outcomes=3）。这里显式用 params，正是为了锁住
        「闸门参数必须走 query」这个易错点 —— 前端若改回 body 传递，
        本测试会立刻变红。
        """
        from unittest.mock import AsyncMock, patch

        fake = AsyncMock(return_value=self._df())
        with patch("easy_tdx.web.routers.chanlun._fetch_request_klines", fake):
            c = self._client()
            body = {
                "market": "SZ",
                "code": "000333",
                "category": "DAY",
                "count": 200,
                "start": 0,
            }
            r = c.post("/api/v1/chanlun/train/session", json=body, params=extra)
            assert r.status_code == 200, r.text
            return r.json()

    def test_train_mode_hides_answers_over_http(self) -> None:
        """mode=train + reveal_limit=0：响应里不得有任何答案或未来收益。"""
        d = self._post(mode="train", reveal_limit=0)
        assert d["mmd_outcomes"] == [], f"训练模式泄未来走势: {d['mmd_outcomes']}"
        leaked = [c for c in d["candidates"] if c["signal"] is not None]
        assert leaked == [], f"开局即泄答案: {leaked}"

    def test_train_mode_reveals_past_answers(self) -> None:
        """揭示到末尾后，已揭示的答案应可取回（供作答后判分）。"""
        d = self._post(mode="train", reveal_limit=10_000)
        assert [c for c in d["candidates"] if c["signal"] is not None], (
            "已揭示的位点应能取回答案，否则作答后无法判分"
        )

    def test_mode_in_body_is_silently_ignored(self) -> None:
        """反向锁定：mode 放 body 时后端收不到，闸门**失效**。

        这条不是要「支持 body」，而是把「必须走 query」这个坑固化下来：
        若有人以为放在 body 里也行，此处会红，提醒他去改前端调用方式。
        """
        from unittest.mock import AsyncMock, patch

        fake = AsyncMock(return_value=self._df())
        with patch("easy_tdx.web.routers.chanlun._fetch_request_klines", fake):
            c = self._client()
            r = c.post(
                "/api/v1/chanlun/train/session",
                json={
                    "market": "SZ",
                    "code": "000333",
                    "category": "DAY",
                    "count": 200,
                    "start": 0,
                    "mode": "review",  # 放错位置
                },
            )
            d = r.json()
        # 期望「未生效」：mode 回落默认 train ⇒ outcomes 被闸门清空
        assert d["mmd_outcomes"] == [], (
            "mode 放 body 竟然生效了？那说明路由签名改过，请同步更新本测试与前端"
        )

    def test_review_mode_keeps_everything(self) -> None:
        """对照组：mode=review 必须保持全量（F2 复盘需要未来收益）。"""
        d = self._post(mode="review")
        assert d["mmd_outcomes"], "复盘模式的 mmd_outcomes 被误删"
        assert [c for c in d["candidates"] if c["signal"] is not None], "复盘模式的答案被误删"
