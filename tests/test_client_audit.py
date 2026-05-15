import json

from src.api.client import FinnegansClient
from src.util.audit import audit_log_path


class _Resp:
    def __init__(self, status_code: int, text: str) -> None:
        self.status_code = status_code
        self.text = text


def test_crear_op_writes_audit_log(monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path))

    client = FinnegansClient("https://api.finneg.com/api", "client-id", "secret")
    monkeypatch.setattr(client, "_get_headers", lambda: {"Authorization": "Bearer token"})

    captured = {}

    def fake_post(url, json=None, headers=None, timeout=None):  # noqa: A002
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        captured["timeout"] = timeout
        return _Resp(201, '{"NumeroComprobante":"OP-0001"}')

    monkeypatch.setattr("src.api.client.httpx.post", fake_post)

    payload = {"Proveedor": "30718308786", "Banco": []}
    result = client.crear_op(payload)

    assert result["NumeroComprobante"] == "OP-0001"
    assert captured["url"].endswith("/ordenPago")
    assert captured["json"] == payload
    assert captured["headers"] == {"Authorization": "Bearer token"}
    assert captured["timeout"] == 30

    rows = audit_log_path().read_text(encoding="utf-8").splitlines()
    assert len(rows) == 1
    entry = json.loads(rows[0])
    assert entry["name"] == "ordenPago"
    assert entry["method"] == "POST"
    assert entry["request"] == payload
    assert entry["response"]["status"] == 201
    assert entry["response"]["body"] == '{"NumeroComprobante":"OP-0001"}'
