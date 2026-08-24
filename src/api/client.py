import time
import logging
from typing import Any

import httpx

from .endpoints import Endpoints
from src.util.audit import record_http_exchange


_LOG = logging.getLogger(__name__)


class AuthError(Exception):
    pass


# Errores de red/timeout: el POST pudo haber llegado a Finnegans sin que
# lleguemos a leer la respuesta, así que se tratan distinto de un ApiError.
NetworkError = httpx.RequestError


class ApiError(Exception):
    def __init__(self, status: int, body: str) -> None:
        super().__init__(f"HTTP {status}: {body}")
        self.status = status
        self.body = body


class FinnegansClient:
    def __init__(self, base_url: str, client_id: str, client_secret: str) -> None:
        self.endpoints = Endpoints(base_url)
        self._client_id = client_id
        self._client_secret = client_secret
        self._token: str | None = None
        self._token_expires_at: float = 0.0

    # ── auth ──────────────────────────────────────────────────────────────

    def _fetch_token(self) -> None:
        resp = httpx.get(
            self.endpoints.token(),
            params={
                "grant_type": "client_credentials",
                "client_id": self._client_id,
                "client_secret": self._client_secret,
            },
            timeout=15,
        )
        if resp.status_code != 200:
            raise AuthError(f"Token request failed {resp.status_code}: {resp.text}")
        # Finnegans devuelve el token como texto plano (UUID), no como JSON
        token = resp.text.strip()
        if not token:
            raise AuthError("Token vacío en la respuesta")
        self._token = token
        self._token_expires_at = time.time() + 3600 - 60

    def _get_headers(self) -> dict:
        if self._token is None or time.time() >= self._token_expires_at:
            self._fetch_token()
        return {"Authorization": f"Bearer {self._token}", "Content-Type": "application/json"}

    # ── requests ──────────────────────────────────────────────────────────

    def post(self, url: str, payload: dict) -> Any:
        try:
            resp = httpx.post(url, json=payload, headers=self._get_headers(), timeout=30)
        except Exception as exc:
            record_http_exchange(
                "ordenPago",
                "POST",
                url,
                request_body=payload,
                error=str(exc),
            )
            raise
        record_http_exchange(
            "ordenPago",
            "POST",
            url,
            request_body=payload,
            response_status=resp.status_code,
            response_body=resp.text,
        )
        _LOG.debug("POST %s -> %s", url, resp.status_code)
        if resp.status_code not in (200, 201):
            raise ApiError(resp.status_code, resp.text[:500])
        return self._parse_response(resp)

    def get(self, url: str) -> Any:
        resp = httpx.get(url, headers=self._get_headers(), timeout=15)
        _LOG.debug("GET %s -> %s", url, resp.status_code)
        if resp.status_code != 200:
            raise ApiError(resp.status_code, resp.text[:500])
        return self._parse_response(resp)

    @staticmethod
    def _parse_response(resp) -> Any:
        import json
        text = resp.text.strip().lstrip("﻿")
        if not text:
            return {}
        try:
            return json.loads(text)
        except Exception:
            return {"raw": text}

    # ── domain helpers ────────────────────────────────────────────────────

    def crear_op(self, payload: dict) -> dict:
        return self.post(self.endpoints.operacion_tesoreria_save(), payload)

    def get_proveedor(self, cuit: str) -> dict:
        if self._token is None or time.time() >= self._token_expires_at:
            self._fetch_token()
        resp = httpx.get(self.endpoints.proveedor(cuit, self._token), timeout=15)
        if resp.status_code != 200:
            raise ApiError(resp.status_code, resp.text[:200])
        return self._parse_response(resp)

    def get_retencion(self, codigo: str) -> dict:
        if self._token is None or time.time() >= self._token_expires_at:
            self._fetch_token()
        resp = httpx.get(self.endpoints.retencion(codigo, self._token), timeout=15)
        if resp.status_code != 200:
            raise ApiError(resp.status_code, resp.text[:200])
        return self._parse_response(resp)

    def get_composicion_saldo_proveedor(
        self, cuit: str, fecha: str, empresa: str = ""
    ) -> list[dict]:
        """`empresa` es el código de negocio limpio («EMPRE01»). Sin él el
        reporte mezcla las sociedades del grupo — ver `endpoints`."""
        if self._token is None or time.time() >= self._token_expires_at:
            self._fetch_token()
        resp = httpx.get(
            self.endpoints.composicion_saldo_proveedor(
                cuit, fecha, self._token, empresa
            ),
            timeout=20,
        )
        if resp.status_code != 200:
            raise ApiError(resp.status_code, resp.text[:200])
        data = self._parse_response(resp)
        return data if isinstance(data, list) else []

    def get_cheques_en_cartera(self, empresa: str, fecha_hasta: str) -> list[dict]:
        """Cheques de terceros en cartera de esa empresa (para endosar).

        `empresa` es el código de negocio limpio («EMPRE01»). Con el ID interno
        («EMPRESA_EMPRE01») Finnegans responde 200 con la lista vacía, así que un
        resultado vacío puede ser eso y no una cartera sin cheques.
        """
        if self._token is None or time.time() >= self._token_expires_at:
            self._fetch_token()
        resp = httpx.get(
            self.endpoints.situacion_cheques(
                self._token, fecha_hasta, empresa=empresa
            ),
            timeout=45,
        )
        if resp.status_code != 200:
            raise ApiError(resp.status_code, resp.text[:200])
        data = self._parse_response(resp)
        return data if isinstance(data, list) else []

    def get_factura_compra(self, documento: str, clave_alterna: str = "") -> dict:
        """La FC se busca por `IdentificacionExterna`, no por el documento interno.

        Coinciden en lo que carga Finnegans, así que con `documento` alcanza casi
        siempre. Lo que carga otro sistema trae `<CUIT>-<comprobante>` ahí y
        responde 404 al documento: para esos se pasa `clave_alterna`.
        """
        if self._token is None or time.time() >= self._token_expires_at:
            self._fetch_token()
        claves = [documento]
        if clave_alterna and clave_alterna != documento:
            claves.append(clave_alterna)
        error: ApiError | None = None
        for clave in claves:
            resp = httpx.get(self.endpoints.factura_compra(clave, self._token), timeout=15)
            if resp.status_code == 200:
                return self._parse_response(resp)
            error = ApiError(resp.status_code, resp.text[:200])
            if resp.status_code != 404:
                break   # 500/403 no se arreglan probando otra clave
        raise error

    def get_cotizacion_dolar(self, fecha: str) -> float:
        """Devuelve la cotización DOL para la fecha dada (yyyy-MM-dd).
        Si no hay dato (feriado/fin de semana), busca hasta 7 días atrás."""
        from datetime import date, timedelta
        if self._token is None or time.time() >= self._token_expires_at:
            self._fetch_token()
        fecha_dt = date.fromisoformat(fecha)
        for dias_atras in range(8):
            f = (fecha_dt - timedelta(days=dias_atras)).strftime("%Y-%m-%d")
            url = self.endpoints.cotizacion(self._token, f)
            resp = httpx.get(url, timeout=15)
            if resp.status_code == 200:
                data = self._parse_response(resp)
                if isinstance(data, list) and data:
                    return float(data[0].get("COTIZACION", 1))
        return 1.0

    def get_talonario_list(self) -> list[dict]:
        if self._token is None or time.time() >= self._token_expires_at:
            self._fetch_token()
        resp = httpx.get(self.endpoints.talonario_list(self._token), timeout=15)
        if resp.status_code != 200:
            raise ApiError(resp.status_code, resp.text[:200])
        data = self._parse_response(resp)
        return data if isinstance(data, list) else []

    def get_talonario(self, codigo: str) -> dict:
        if self._token is None or time.time() >= self._token_expires_at:
            self._fetch_token()
        resp = httpx.get(self.endpoints.talonario(codigo, self._token), timeout=15)
        if resp.status_code != 200:
            raise ApiError(resp.status_code, resp.text[:200])
        return self._parse_response(resp)

    def get_analisis_retencion(
        self,
        cuit: str,
        fecha_desde: str,
        fecha_hasta: str,
        empresa: str = "",
        modo_emision: int = 2,
    ) -> list[dict]:
        if self._token is None or time.time() >= self._token_expires_at:
            self._fetch_token()
        url = self.endpoints.analisis_retencion(
            self._token, cuit, fecha_desde, fecha_hasta, empresa, modo_emision
        )
        try:
            resp = httpx.get(url, timeout=20)
        except Exception as exc:
            record_http_exchange(
                "analisisRetencion",
                "GET",
                url,
                error=str(exc),
            )
            raise
        record_http_exchange(
            "analisisRetencion",
            "GET",
            url,
            response_status=resp.status_code,
            response_body=resp.text,
        )
        if resp.status_code != 200:
            raise ApiError(resp.status_code, resp.text[:200])
        data = self._parse_response(resp)
        return data if isinstance(data, list) else []

    def get_empresa_list(self) -> list[dict]:
        if self._token is None or time.time() >= self._token_expires_at:
            self._fetch_token()
        resp = httpx.get(self.endpoints.empresa_list(self._token), timeout=15)
        if resp.status_code != 200:
            raise ApiError(resp.status_code, resp.text[:200])
        data = self._parse_response(resp)
        return data if isinstance(data, list) else []

    def get_cuenta_list(self) -> list[dict]:
        if self._token is None or time.time() >= self._token_expires_at:
            self._fetch_token()
        resp = httpx.get(self.endpoints.cuenta_list(self._token), timeout=15)
        if resp.status_code != 200:
            raise ApiError(resp.status_code, resp.text[:200])
        data = self._parse_response(resp)
        return data if isinstance(data, list) else []

    def get_banco_list(self) -> list[dict]:
        """Bancos con su código. Necesario para el endoso: el reporte de cartera
        trae el nombre del banco del librador y la OP pide el código."""
        if self._token is None or time.time() >= self._token_expires_at:
            self._fetch_token()
        resp = httpx.get(self.endpoints.banco_list(self._token), timeout=20)
        if resp.status_code != 200:
            raise ApiError(resp.status_code, resp.text[:200])
        data = self._parse_response(resp)
        return data if isinstance(data, list) else []

    def get_tipo_operacion_bancaria_list(self) -> list[dict]:
        if self._token is None or time.time() >= self._token_expires_at:
            self._fetch_token()
        resp = httpx.get(self.endpoints.tipo_operacion_bancaria_list(self._token), timeout=15)
        if resp.status_code != 200:
            raise ApiError(resp.status_code, resp.text[:200])
        data = self._parse_response(resp)
        return data if isinstance(data, list) else []

    def ping(self) -> bool:
        try:
            self._fetch_token()
            return True
        except Exception:
            return False
