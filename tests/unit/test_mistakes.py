"""web/train_store.py V426 learn_mistakes 错题集 测试。"""

from __future__ import annotations

from pathlib import Path

from easy_tdx.web.train_store import TrainScoreStore


class TestMistakes:
    def test_add_and_list(self, tmp_path: Path) -> None:
        store = TrainScoreStore(tmp_path / "s.db")
        store.add_mistake(
            {
                "player": "甲",
                "symbol": "SH600519",
                "category": "DAY",
                "difficulty": "hard",
                "question_date": "2024-03-15",
                "signal_type": "3buy",
                "user_choice": "sell",
                "actual": "buy",
                "explanation": "模型识别为 3buy（置信度 92%），V102 建议：买入",
            }
        )
        rows = store.list_mistakes(player="甲")
        assert len(rows) == 1
        assert rows[0]["signal_type"] == "3buy"
        assert rows[0]["user_choice"] == "sell"

    def test_filter_by_category(self, tmp_path: Path) -> None:
        store = TrainScoreStore(tmp_path / "s.db")
        for cat in ("DAY", "MIN_5"):
            store.add_mistake(
                {
                    "player": "甲",
                    "symbol": "SZ000001",
                    "category": cat,
                    "difficulty": "easy",
                    "signal_type": "1buy",
                    "user_choice": "hold",
                    "actual": "buy",
                    "explanation": "x",
                }
            )
        assert len(store.list_mistakes(player="甲")) == 2
        assert len(store.list_mistakes(player="甲", category="DAY")) == 1
