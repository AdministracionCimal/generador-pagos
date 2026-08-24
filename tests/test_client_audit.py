import json

import pytest

from src.api.client import ApiError, FinnegansClient
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

    payload = {"Proveedor": "30111111117", "Banco": []}
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


# ── /facturaCompra: se busca por IdentificacionExterna ───────────────────────

_FC_OK = '{"Conceptos":[{"ConceptoImporteGravado":2400000.0}],"ImporteTotalControl":2904000.0}'
_404 = '{"error":"Not Found: ","status":404}'


def _cliente_con(monkeypatch, respuestas: dict):
    """Cliente cuyo GET responde según la clave que aparezca en la URL."""
    client = FinnegansClient("https://api.finneg.com/api", "id", "secret")
    monkeypatch.setattr(client, "_fetch_token", lambda: None)
    client._token = "tok"
    client._token_expires_at = 1e12
    pedidas: list[str] = []

    def fake_get(url, headers=None, timeout=None, **kw):
        from urllib.parse import unquote
        pedidas.append(url)
        for clave, resp in respuestas.items():
            if unquote(url).split("/facturaCompra/")[1].startswith(clave):
                return resp
        return _Resp(404, _404)

    monkeypatch.setattr("src.api.client.httpx.get", fake_get)
    return client, pedidas


def test_factura_compra_resuelve_por_documento_sin_pedir_la_alterna(monkeypatch):
    client, pedidas = _cliente_con(monkeypatch, {"FC - 20402": _Resp(200, _FC_OK)})

    fc = client.get_factura_compra("FC - 20402", "20313144411-A-0002-00000190")

    assert fc["ImporteTotalControl"] == 2904000.0
    assert len(pedidas) == 1, "no hace falta el reintento si el documento resuelve"


def test_factura_compra_reintenta_con_la_identificacion_externa(monkeypatch):
    # Lo que carga el otro sistema: 404 al documento, 200 a <CUIT>-<comprobante>.
    client, pedidas = _cliente_con(
        monkeypatch, {"20313144411-A-0002-00000196": _Resp(200, _FC_OK)}
    )

    fc = client.get_factura_compra("FC - 22219", "20313144411-A-0002-00000196")

    assert fc["ImporteTotalControl"] == 2904000.0
    assert len(pedidas) == 2


def test_factura_compra_que_no_existe_sigue_fallando(monkeypatch):
    client, _ = _cliente_con(monkeypatch, {})

    with pytest.raises(ApiError) as exc:
        client.get_factura_compra("FC - 99999", "20313144411-A-0002-99999999")

    assert exc.value.status == 404


def test_factura_compra_no_reintenta_ante_un_error_del_servidor(monkeypatch):
    # Un 500 no se arregla probando otra clave: cortar en vez de duplicar carga.
    client, pedidas = _cliente_con(monkeypatch, {"FC - 22219": _Resp(500, "boom")})

    with pytest.raises(ApiError) as exc:
        client.get_factura_compra("FC - 22219", "20313144411-A-0002-00000196")

    assert exc.value.status == 500
    assert len(pedidas) == 1


def test_factura_compra_sin_clave_alterna_no_reintenta(monkeypatch):
    client, pedidas = _cliente_con(monkeypatch, {})

    with pytest.raises(ApiError):
        client.get_factura_compra("FC - 22219")

    assert len(pedidas) == 1
