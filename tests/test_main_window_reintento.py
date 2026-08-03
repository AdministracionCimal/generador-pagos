"""Protecciones contra reenvío duplicado y contra numeración de cheques desfasada."""
from dataclasses import replace
from datetime import date
from decimal import Decimal

import httpx
import pytest
from PyQt6.QtCore import QCoreApplication

from src.domain.models import ItemFactura, OpPago, ProveedorTanda
from src.ui.main_window import (
    _ProcesarWorker,
    numero_cheque_desfasado,
    proveedores_pendientes,
)


def _prov(nombre: str, cuit: str) -> ProveedorTanda:
    return ProveedorTanda(cuit=cuit, nombre=nombre)


def _resultado(estado: str) -> dict:
    return {"estado": estado, "detalle": ""}


class TestProveedoresPendientes:
    def test_saca_los_confirmados_y_deja_los_que_fallaron(self):
        a, b, c = _prov("A", "30111111117"), _prov("B", "30222222226"), _prov("C", "30333333335")
        ops = [OpPago(proveedor=p) for p in (a, b, c)]
        resultados = [_resultado("OK"), _resultado("ERROR"), _resultado("OK")]

        quedan = proveedores_pendientes([a, b, c], ops, resultados)

        assert [p.nombre for p in quedan] == ["B"]

    def test_reconoce_al_proveedor_aunque_la_op_use_una_copia(self):
        # _construir_ops hace dataclasses.replace al filtrar ítems sin saldo:
        # la OP lleva otro objeto con el mismo CUIT y nombre.
        original = _prov("A", "30111111117")
        op = OpPago(proveedor=replace(original, items=[]))

        quedan = proveedores_pendientes([original], [op], [_resultado("OK")])

        assert quedan == []

    def test_no_saca_nada_si_todo_fallo(self):
        a, b = _prov("A", "30111111117"), _prov("B", "30222222226")
        ops = [OpPago(proveedor=a), OpPago(proveedor=b)]

        quedan = proveedores_pendientes([a, b], ops, [_resultado("ERROR")] * 2)

        assert [p.nombre for p in quedan] == ["A", "B"]

    def test_conserva_los_manuales_que_nunca_tuvieron_op(self):
        pagado, manual = _prov("Pagado", "30111111117"), _prov("Manual", "30222222226")
        ops = [OpPago(proveedor=pagado)]

        quedan = proveedores_pendientes([pagado, manual], ops, [_resultado("OK")])

        assert [p.nombre for p in quedan] == ["Manual"]

    def test_homonimos_con_cuit_distinto_no_se_confunden(self):
        uno, dos = _prov("SERVICIOS SA", "30111111117"), _prov("SERVICIOS SA", "30222222226")
        ops = [OpPago(proveedor=uno), OpPago(proveedor=dos)]

        quedan = proveedores_pendientes([uno, dos], ops, [_resultado("OK"), _resultado("ERROR")])

        assert [p.cuit for p in quedan] == ["30222222226"]


class TestNumeroChequeDesfasado:
    def test_coinciden(self):
        assert numero_cheque_desfasado("73189914", 73189914) is None

    def test_erp_adelantado_otro_usuario_emitio(self):
        assert numero_cheque_desfasado("73189920", 73189914) == 73189920

    def test_erp_atrasado_se_saltearon_cheques(self):
        assert numero_cheque_desfasado("73189910", 73189914) == 73189910

    def test_dato_no_utilizable(self):
        for valor in ("", "   ", "N/D", None):
            assert numero_cheque_desfasado(valor, 73189914) is None

    def test_tolera_espacios(self):
        assert numero_cheque_desfasado(" 73189920 ", 73189914) == 73189920


@pytest.fixture(scope="module")
def qt_app():
    """QCoreApplication (sin GUI) para que los signals del worker funcionen."""
    return QCoreApplication.instance() or QCoreApplication([])


class TestProcesarWorkerCorteDeRed:
    def _op(self) -> OpPago:
        prov = ProveedorTanda(
            cuit="30111111117",
            nombre="TEST SA",
            items=[ItemFactura("FC - 1", "A-1", "", Decimal("100"), None, "Ch 10/09")],
        )
        return OpPago(proveedor=prov, fecha=date(2026, 8, 3))

    def _correr(self, qt_app, client) -> dict:
        worker = _ProcesarWorker([self._op()], client)
        capturado: list = []
        worker.terminado.connect(capturado.append)
        worker.run()
        return capturado[0][0]

    def test_timeout_avisa_que_no_hay_confirmacion(self, qt_app):
        class ClienteQueCortaLaConexion:
            def crear_op(self, payload):
                raise httpx.ReadTimeout("timed out")

        res = self._correr(qt_app, ClienteQueCortaLaConexion())

        assert res["estado"] == "ERROR"
        assert "SIN CONFIRMACION" in res["detalle"]
        assert "antes de reintentar" in res["detalle"].lower()

    def test_alta_exitosa_devuelve_el_numero(self, qt_app):
        class ClienteOk:
            def crear_op(self, payload):
                return {"NumeroComprobante": "OP-0004-00022013"}

        res = self._correr(qt_app, ClienteOk())

        assert res["estado"] == "OK"
        assert res["numero_real"] == "OP-0004-00022013"
