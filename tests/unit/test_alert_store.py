"""全局提醒流（V718）单元测试：去重、来源过滤、有界、清空。"""

from __future__ import annotations

from easy_tdx.web.alert_store import clear_alerts, push_alert, recent_alerts


def test_push_and_recent_order() -> None:
    """写入后最新在前。"""
    clear_alerts()
    push_alert({"stock": "SH600519", "action": "买入", "source": "monitor"})
    push_alert({"stock": "SZ000001", "action": "卖出", "source": "dashboard"})
    items = recent_alerts(10)
    assert [a["stock"] for a in items] == ["SZ000001", "SH600519"]
    assert items[0]["source"] == "dashboard"


def test_key_dedup() -> None:
    """同键提醒只保留一条。"""
    clear_alerts()
    push_alert({"key": "k1", "stock": "A", "action": "买入"})
    push_alert({"key": "k1", "stock": "A", "action": "买入"})
    assert len(recent_alerts(10)) == 1


def test_source_filter() -> None:
    """按来源过滤（monitor/dashboard）。"""
    clear_alerts()
    push_alert({"stock": "A", "action": "买入", "source": "monitor"})
    push_alert({"stock": "B", "action": "卖出", "source": "dashboard"})
    mon = recent_alerts(10)
    assert {a["source"] for a in mon} == {"monitor", "dashboard"}


def test_bounded_feed() -> None:
    """超过上限丢弃最旧（deque 有界）。"""
    clear_alerts()
    for i in range(250):
        push_alert({"key": f"k{i}", "stock": f"S{i}", "action": "买入"})
    items = recent_alerts(500)
    assert len(items) == 200
    # 最新在前：最后写入的 k249 在最前
    assert items[0]["stock"] == "S249"


def test_alerts_endpoint() -> None:
    """GET /monitor/alerts 返回提醒流；clear 清空。"""
    from fastapi.testclient import TestClient

    from easy_tdx.web import create_app
    from easy_tdx.web.alert_store import clear_alerts, push_alert

    clear_alerts()
    push_alert({"stock": "SH600519", "action": "买入", "source": "dashboard", "entry": 10.0})
    app = create_app()
    with TestClient(app) as client:
        r = client.get("/api/v1/monitor/alerts")
        assert r.status_code == 200
        d = r.json()
        assert d.get("count", 0) >= 1
        assert any(a.get("stock") == "SH600519" for a in d.get("alerts") or [])
        r2 = client.post("/api/v1/monitor/alerts/clear")
        assert r2.status_code == 200
        d2 = client.get("/api/v1/monitor/alerts").json()
        assert d2.get("count") == 0
