
from pathlib import Path

def test_gateway_transport_contract():
    text = Path("app/main.py").read_text(encoding="utf-8")
    assert 'type="pong"' in text
    assert 'type="snapshot_ack"' in text
    assert 'type="snapshot_error"' in text
    assert "Ошибка обработки облачного снимка" in text

def test_agent_transport_contract():
    path = Path("../app/websocket_agent_client.py")
    text = path.read_text(encoding="utf-8")
    assert 'message.type == "pong"' in text
    assert 'message.type == "snapshot_ack"' in text
    assert 'message.type == "snapshot_error"' in text
    assert "ping_interval=15" in text
    assert "ping_timeout=45" in text
    assert '"agent_version": "31.0.0"' in text
