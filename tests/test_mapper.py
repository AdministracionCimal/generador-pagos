"""
Golden-file test for mapper.armar_post().

Reference: tests/fixtures/response_OP-0004-00021922.json
Provider: C.O.F. S.A.S. (CUIT 30718308786)
3 items: MOVFONDOS-10845, MOVFONDOS-10846, FC-21562 → 8 checks total

Intentionally skipped / deferred to Sprint 7:
- Banco importe for FC checks: golden used net-of-retention amounts (12039500 - 24707.08 retention).
  Our mapper sends gross (Retencion: []); Finnegans computes retention server-side.
  Exact Banco amounts for FC will be validated after the first live POST.
- CUIT: not present in DM sheet; set manually here from golden file.
"""
import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from src.domain.fraccionador import fraccionar_proveedor
from src.domain.mapper import armar_post
from src.domain.models import OpPago
from src.excel.dm_reader import leer_dm

FIXTURE_XLS = Path(__file__).parent / "fixtures" / "07.05.2025.xlsx"
FIXTURE_JSON = Path(__file__).parent / "fixtures" / "response_OP-0004-00021922.json"

FECHA = date(2026, 5, 8)
NUMERO_DESDE = 73189907
CHEQUERA = "MACRO CPDProv 03"
BANCO = "00285"
CUENTA_BANCO = "02.01.04.01.0009"
CUIT = "30718308786"
CUENTA_PROVEEDOR = "02.01.01.01.0001"


@pytest.fixture(scope="module")
def golden():
    return json.loads(FIXTURE_JSON.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def resultado(golden):
    proveedores = leer_dm(FIXTURE_XLS)
    cof = next(p for p in proveedores if "C.O.F" in p.nombre)
    cof.cuit = CUIT
    cheques, _ = fraccionar_proveedor(cof.items, numero_desde=NUMERO_DESDE,
                                      fecha_emision=FECHA, anio=2026)
    op = OpPago(
        proveedor=cof,
        cheques=cheques,
        chequera_codigo=CHEQUERA,
        banco_codigo=BANCO,
        cuenta_banco_codigo=CUENTA_BANCO,
        cuenta_proveedor_codigo=CUENTA_PROVEEDOR,
        fecha=FECHA,
    )
    return armar_post(op)


@pytest.mark.skipif(not FIXTURE_XLS.exists() or not FIXTURE_JSON.exists(),
                    reason="fixtures no disponibles")
class TestMapperGolden:
    def test_campos_meta(self, resultado, golden):
        assert resultado["EmpresaCodigo"] == golden["EmpresaCodigo"]
        assert resultado["Proveedor"] == golden["Proveedor"]
        assert resultado["TransaccionTipoCodigo"] == golden["TransaccionTipoCodigo"]
        assert resultado["TransaccionSubtipoCodigo"] == golden["TransaccionSubtipoCodigo"]
        assert resultado["DiferenciaCambio"] == 0
        assert resultado["ImportacionEcheq"] is False
        assert resultado["USR_ComboOC"] is None
        assert resultado["CajaCodigo"] is None
        assert resultado["Retencion"] == []
        assert resultado["Efectivo"] == []
        assert resultado["Otros"] == []

    def test_banco_cantidad_cheques(self, resultado, golden):
        assert len(resultado["Banco"]) == len(golden["Banco"]) == 8

    def test_banco_campos_estructurales(self, resultado):
        for entry in resultado["Banco"]:
            assert entry["OperacionBancariaCodigo"] == "EMCHPROP"
            assert entry["CuentaCodigo"] == CUENTA_BANCO
            assert entry["DebeHaber"] == -1
            assert entry["MonedaCodigo"] == "PES"
            assert entry["ChequeraCodigo"] == CHEQUERA
            assert entry["BancoCodigo"] == BANCO
            assert entry["DimensionDistribucion"] == []

    def test_banco_numeros_fisicos(self, resultado, golden):
        nros_nuestros = [e["NumeroDocumentoFisico"] for e in resultado["Banco"]]
        nros_golden = [e["NumeroDocumentoFisico"] for e in golden["Banco"]]
        assert nros_nuestros == nros_golden

    def test_banco_fechas_vencimiento(self, resultado, golden):
        vtos_nuestros = sorted(e["FechaVencimientoDocumentoFisico"] for e in resultado["Banco"])
        vtos_golden   = sorted(e["FechaVencimientoDocumentoFisico"] for e in golden["Banco"])
        assert vtos_nuestros == vtos_golden

    def test_banco_fecha_emision(self, resultado):
        for entry in resultado["Banco"]:
            assert entry["FechaDocumentoFisico"] == "2026-05-08"

    def test_banco_movfondos_importes(self, resultado, golden):
        # MOVFONDOS importes should match golden exactly (no retention involved).
        # Use amount threshold to identify MOVFONDOS (~917K) vs FC checks (~2M).
        _UMBRAL = 1_500_000
        movfondos_golden  = sorted(e["ImporteMonTransaccion"] for e in golden["Banco"]   if e["ImporteMonTransaccion"] < _UMBRAL)
        movfondos_nuestros = sorted(e["ImporteMonTransaccion"] for e in resultado["Banco"] if e["ImporteMonTransaccion"] < _UMBRAL)
        assert len(movfondos_nuestros) == len(movfondos_golden) == 2
        for nuestro, ref in zip(movfondos_nuestros, movfondos_golden):
            assert nuestro == pytest.approx(ref, abs=0.01)

    def test_banco_fc_importes_gross(self, resultado):
        # FC - 21562: gross 12039500 / 6, last absorbs centavos
        _UMBRAL = 1_500_000
        fc_checks = [e for e in resultado["Banco"] if e["ImporteMonTransaccion"] >= _UMBRAL]
        total = sum(e["ImporteMonTransaccion"] for e in fc_checks)
        assert total == pytest.approx(12039500.0, abs=0.01)
        assert len(fc_checks) == 6

    def test_ctacte_cantidad(self, resultado, golden):
        assert len(resultado["CtaCte"]) == len(golden["CtaCte"]) == 3

    def test_ctacte_importes(self, resultado, golden):
        for i, (nuestro, ref) in enumerate(zip(resultado["CtaCte"], golden["CtaCte"])):
            assert nuestro["ImporteMonTransaccion"] == pytest.approx(
                ref["ImporteMonTransaccion"], abs=0.01
            ), f"CtaCte[{i}] importe mismatch"

    def test_ctacte_aplicacion_origen(self, resultado, golden):
        for nuestro, ref in zip(resultado["CtaCte"], golden["CtaCte"]):
            assert nuestro["AplicacionOrigen"] == ref["AplicacionOrigen"]

    def test_ctacte_descripcion(self, resultado, golden):
        for nuestro, ref in zip(resultado["CtaCte"], golden["CtaCte"]):
            assert nuestro["Descripcion"] == ref["Descripcion"]

    def test_ctacte_campos_estructurales(self, resultado):
        for entry in resultado["CtaCte"]:
            assert entry["CuentaCodigo"] == CUENTA_PROVEEDOR
            assert entry["DebeHaber"] == 1
            assert entry["MonedaCodigo"] == "PES"
            assert entry["DimensionDistribucion"] == []
