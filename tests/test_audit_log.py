import json

from src.util.audit import audit_log_path, record_http_exchange


def test_record_http_exchange_persists_jsonl(monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path))

    record_http_exchange(
        "analisisRetencion",
        "get",
        "https://api.finneg.com/api/reports/analisisRetencion?ACCESS_TOKEN=abc123&foo=bar",
        response_status=200,
        response_body='[{"ok": true}]',
    )

    path = audit_log_path()
    assert path.exists()

    rows = path.read_text(encoding="utf-8").splitlines()
    assert len(rows) == 1

    entry = json.loads(rows[0])
    assert entry["name"] == "analisisRetencion"
    assert entry["method"] == "GET"
    assert entry["url"].endswith("ACCESS_TOKEN=%5BREDACTED%5D&foo=bar")
    assert entry["response"]["status"] == 200
    assert entry["response"]["body"] == '[{"ok": true}]'
