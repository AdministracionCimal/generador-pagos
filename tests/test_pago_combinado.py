"""Pago combinado: del proveedor y la cartera al JSON del POST.

El test que importa es `TestContraLaOpReal`: arma el mismo pago que una OP que se
cargó a mano en Finnegans (3 endosos + 8 cheques propios) y compara el JSON que
genera el mapper contra el que devolvió el ERP.
"""
import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from src.domain.bancos import mapa_por_nombre
from src.domain.cartera import leer_cartera
from src.domain.clasificador import clasificar
from src.domain.forma_pago import RepartoError, parsear_tramos
from src.domain.mapper import armar_post
from src.domain.models import ItemFactura, Modalidad, OpPago, ProveedorTanda
from src.domain.pago_combinado import armar

FIXTURE = Path(__file__).parent / "fixtures" / "response_OP-0004-00022502_endosos.json"
OP_REAL = json.loads(FIXTURE.read_text(encoding="utf-8"))
HOY = date(2026, 7, 27)

BANCOS = [
    {"codigo": "00017", "nombre": "BBVA BANCO FRANCES S.A."},
    {"codigo": "00034", "nombre": "BANCO PATAGONIA S.A."},
    {"codigo": "00285", "nombre": "BANCO MACRO S.A."},
]
MAPA_BANCOS = mapa_por_nombre(BANCOS)


def _cartera_de(op: dict) -> list:
    """Reconstruye la cartera que había antes de endosar, desde la OP real."""
    filas = []
    for b in op["Banco"]:
        if b["OperacionBancariaCodigo"] != "CHENDOSADOS":
            continue
        nombre_banco = next(x["nombre"] for x in BANCOS if x["codigo"] == b["BancoCodigo"])
        filas.append({
            "DOCUMENTOFISICOID": b["DocumentoFisicoID"],
            "NUMERO": b["NumeroDocumentoFisico"],
            "NROCHEQUEELECTRONICO": b["NumeroDocumentoFisico"],
            "BANCO": nombre_banco,
            "TERCERO": "LIBRADOR SA",
            "CUITLIBRADOR": "30-11111111-7",
            "FECHAEMISION": _iso_a_ddmmyyyy(b["FechaDocumentoFisico"]),
            "FECHAVENCIMIENTO": _iso_a_ddmmyyyy(b["FechaVencimientoDocumentoFisico"]),
            "IMPORTEMONTRANSACCION": b["ImporteMonTransaccion"],
            "EMPRESA": "CIMALCO NEUQUEN S.A.",
            "ESTADO": "En Cartera",
        })
    return leer_cartera(filas)


def _iso_a_ddmmyyyy(iso: str) -> str:
    a, m, d = iso.split("-")
    return f"{d}-{m}-{a}"


def _proveedor_de(op: dict) -> ProveedorTanda:
    """Proveedor con los ítems tal como los aplica la OP real."""
    items = [
        ItemFactura(
            documento=c["AplicacionOrigen"],
            comprobante=c["Descripcion"],
            descripcion="",
            # En el Excel el signo va al revés: dm_reader lo invierte al leer.
            importe=Decimal(str(c["ImporteMonTransaccion"])) * (1 if c["DebeHaber"] == 1 else -1),
            fecha_vto=None,
            modalidad_pago=_forma_de_pago(op),
        )
        for c in op["CtaCte"]
    ]
    return ProveedorTanda(cuit=op["Proveedor"], nombre="PROVEEDOR SA", items=items)


def _forma_de_pago(op: dict) -> str:
    """La «Forma de pago» que produciría esta OP: endosos + cheques por fecha."""
    endosos = [b for b in op["Banco"] if b["OperacionBancariaCodigo"] == "CHENDOSADOS"]
    propios = [b for b in op["Banco"] if b["OperacionBancariaCodigo"] == "EMCHPROP"]
    numeros = " - ".join(b["NumeroDocumentoFisico"] for b in endosos)
    fechas = " - ".join(
        f"{b['FechaVencimientoDocumentoFisico'][8:10]}/{b['FechaVencimientoDocumentoFisico'][5:7]}"
        for b in propios
    )
    return f"Endoso {numeros} + Ch {fechas}"


def _retencion_total(op: dict) -> Decimal:
    return sum((Decimal(str(r["Importe"])) for r in op["Retencion"]), Decimal("0"))


def _primer_numero_de_cheque_propio(op: dict) -> int:
    """La numeración arranca donde arrancó la OP real (los números del fixture
    están anonimizados, así que se lee de ahí y no se hardcodea)."""
    return int(next(
        b["NumeroDocumentoFisico"] for b in op["Banco"]
        if b["OperacionBancariaCodigo"] == "EMCHPROP"
    ))


class TestContraLaOpReal:
    @pytest.fixture(scope="class")
    def armado(self):
        proveedor = clasificar(_proveedor_de(OP_REAL))
        return proveedor, armar(
            proveedor,
            proveedor.tramos,
            retencion_total=_retencion_total(OP_REAL),
            cheques_cartera=_cartera_de(OP_REAL),
            mapa_bancos=MAPA_BANCOS,
            numero_desde=_primer_numero_de_cheque_propio(OP_REAL),
            fecha_emision=HOY,
        )

    def test_se_clasifica_como_combinado(self, armado):
        proveedor, _ = armado
        assert proveedor.modalidad == Modalidad.COMBINADO
        assert [t.tipo for t in proveedor.tramos] == ["ENDOSO", "CHEQUE"]

    def test_los_endosos_van_por_su_nominal(self, armado):
        _, pago = armado
        esperados = [
            Decimal(str(b["ImporteMonTransaccion"]))
            for b in OP_REAL["Banco"] if b["OperacionBancariaCodigo"] == "CHENDOSADOS"
        ]
        assert [e.importe for e in pago.endosos] == esperados

    def test_los_endosos_llevan_el_documento_fisico_y_el_banco_del_librador(self, armado):
        _, pago = armado
        reales = [b for b in OP_REAL["Banco"] if b["OperacionBancariaCodigo"] == "CHENDOSADOS"]
        assert [e.documento_fisico_id for e in pago.endosos] == [
            b["DocumentoFisicoID"] for b in reales
        ]
        assert [e.banco_codigo for e in pago.endosos] == [b["BancoCodigo"] for b in reales]

    def test_los_cheques_propios_reproducen_importes_y_vencimientos(self, armado):
        _, pago = armado
        reales = [b for b in OP_REAL["Banco"] if b["OperacionBancariaCodigo"] == "EMCHPROP"]
        assert [c.importe for c in pago.cheques] == [
            Decimal(str(b["ImporteMonTransaccion"])) for b in reales
        ]
        assert [c.fecha_vencimiento.isoformat() for c in pago.cheques] == [
            b["FechaVencimientoDocumentoFisico"] for b in reales
        ]

    def test_no_hay_tramo_de_transferencia(self, armado):
        _, pago = armado
        assert pago.importe_transferencia is None

    def test_el_total_del_pago_es_el_neto(self, armado):
        _, pago = armado
        banco_real = sum(
            (Decimal(str(b["ImporteMonTransaccion"])) for b in OP_REAL["Banco"]),
            Decimal("0"),
        )
        assert pago.total == banco_real

    def test_el_json_del_post_coincide_con_la_op_real(self, armado):
        """Comparación campo por campo de la sección Banco."""
        proveedor, pago = armado
        op = OpPago(
            proveedor=proveedor,
            cheques=pago.cheques,
            endosos=pago.endosos,
            importe_transferencia=pago.importe_transferencia,
            chequera_codigo="MACRO CPDProv 04",
            banco_codigo="00285",
            cuenta_banco_codigo="02.01.04.01.0009",
            empresa_codigo="EMPRE01",
            fecha=HOY,
        )
        generado = armar_post(op)

        campos = [
            "OperacionBancariaCodigo", "CuentaCodigo", "DebeHaber",
            "ImporteMonTransaccion", "MonedaCodigo", "ImporteMonPrincipal",
            "NumeroDocumentoFisico", "FechaDocumentoFisico",
            "FechaVencimientoDocumentoFisico", "ChequeraCodigo", "BancoCodigo",
        ]
        for i, (esperado, obtenido) in enumerate(zip(OP_REAL["Banco"], generado["Banco"])):
            for campo in campos:
                assert obtenido[campo] == esperado[campo], f"Banco[{i}].{campo}"
            if esperado["OperacionBancariaCodigo"] == "CHENDOSADOS":
                # El del cheque en cartera: lo manda la app.
                assert obtenido["DocumentoFisicoID"] == esperado["DocumentoFisicoID"]
            else:
                # En un cheque propio lo asigna Finnegans al crearlo: se manda null.
                assert obtenido["DocumentoFisicoID"] is None
        assert len(generado["Banco"]) == len(OP_REAL["Banco"])

    def test_la_cta_cte_del_post_coincide_con_la_op_real(self, armado):
        proveedor, pago = armado
        op = OpPago(proveedor=proveedor, cheques=pago.cheques, endosos=pago.endosos, fecha=HOY)
        generado = armar_post(op)
        for esperado, obtenido in zip(OP_REAL["CtaCte"], generado["CtaCte"]):
            assert obtenido["DebeHaber"] == esperado["DebeHaber"]
            assert obtenido["ImporteMonTransaccion"] == esperado["ImporteMonTransaccion"]
            assert obtenido["AplicacionOrigen"] == esperado["AplicacionOrigen"]


class TestChequeMasTransferencia:
    def _proveedor(self, forma: str, importe: str = "1000000") -> ProveedorTanda:
        return clasificar(ProveedorTanda(
            cuit="30111111117", nombre="ACME SA",
            items=[ItemFactura("FC - 1", "A-1", "", Decimal(importe), None, forma)],
        ))

    def test_la_transferencia_absorbe_la_retencion(self):
        proveedor = self._proveedor("Ch 10/09 + transferencia 30%")
        assert proveedor.modalidad == Modalidad.COMBINADO

        pago = armar(
            proveedor, proveedor.tramos,
            retencion_total=Decimal("50000"),
            cheques_cartera=[], mapa_bancos={},
            numero_desde=100, fecha_emision=HOY,
        )
        assert pago.importe_transferencia == Decimal("250000")
        assert sum(c.importe for c in pago.cheques) == Decimal("700000")
        assert pago.total == Decimal("950000")

    def test_el_post_lleva_los_dos_tramos(self):
        proveedor = self._proveedor("Ch 10/09 - 20/09 + transferencia 40%")
        pago = armar(
            proveedor, proveedor.tramos, Decimal("0"), [], {},
            numero_desde=500, fecha_emision=HOY,
        )
        op = OpPago(
            proveedor=proveedor, cheques=pago.cheques,
            importe_transferencia=pago.importe_transferencia,
            cuenta_banco_codigo="01.01.01.02.0006", fecha=HOY,
        )
        banco = armar_post(op)["Banco"]
        assert [b["OperacionBancariaCodigo"] for b in banco] == [
            "EMCHPROP", "EMCHPROP", "TLote",
        ]
        assert banco[-1]["ImporteMonTransaccion"] == 400000.0
        assert banco[-1]["ChequeraCodigo"] is None
        assert sum(b["ImporteMonTransaccion"] for b in banco) == 1000000.0


class TestCasosQueVanAManual:
    def _proveedor(self, forma: str, importe: str) -> ProveedorTanda:
        return ProveedorTanda(
            cuit="30111111117", nombre="ACME SA",
            items=[ItemFactura("FC - 1", "A-1", "", Decimal(importe), None, forma)],
            modalidad=Modalidad.COMBINADO,
            tramos=parsear_tramos(forma),
        )

    def _cartera(self, numero: str, importe: str) -> list:
        return leer_cartera([{
            "DOCUMENTOFISICOID": 1, "NUMERO": numero, "NROCHEQUEELECTRONICO": numero,
            "BANCO": "BANCO MACRO S.A.", "TERCERO": "X", "CUITLIBRADOR": "30-1-7",
            "FECHAEMISION": "01-07-2026", "FECHAVENCIMIENTO": "01-09-2026",
            "IMPORTEMONTRANSACCION": importe, "EMPRESA": "CIMALCO NEUQUEN S.A.",
        }])

    def test_endoso_que_deja_saldo_a_favor(self):
        proveedor = self._proveedor("Endoso 12345", "1000000")
        with pytest.raises(RepartoError, match="a favor del proveedor"):
            armar(proveedor, proveedor.tramos, Decimal("0"),
                  self._cartera("12345", "1200000"), MAPA_BANCOS, 1, HOY)

    def test_endoso_que_no_cubre_el_total(self):
        proveedor = self._proveedor("Endoso 12345", "1000000")
        with pytest.raises(RepartoError, match="faltan"):
            armar(proveedor, proveedor.tramos, Decimal("0"),
                  self._cartera("12345", "800000"), MAPA_BANCOS, 1, HOY)

    def test_endoso_que_cierra_exacto_si_funciona(self):
        proveedor = self._proveedor("Endoso 12345", "1000000")
        pago = armar(proveedor, proveedor.tramos, Decimal("0"),
                     self._cartera("12345", "1000000"), MAPA_BANCOS, 1, HOY)
        assert pago.total == Decimal("1000000")
        assert pago.endosos[0].numero == "12345"

    def test_cheque_que_no_esta_en_cartera(self):
        proveedor = self._proveedor("Endoso 99999 + Ch 10/09", "1000000")
        with pytest.raises(RepartoError, match="no se encontró en cartera"):
            armar(proveedor, proveedor.tramos, Decimal("0"),
                  self._cartera("12345", "500000"), MAPA_BANCOS, 1, HOY)

    def test_banco_que_no_se_puede_resolver(self):
        """Antes que endosar con el banco equivocado, carga manual."""
        proveedor = self._proveedor("Endoso 12345 + Ch 10/09", "1000000")
        with pytest.raises(RepartoError, match="código del banco"):
            armar(proveedor, proveedor.tramos, Decimal("0"),
                  self._cartera("12345", "400000"), mapa_bancos={}, numero_desde=1,
                  fecha_emision=HOY)

    def test_el_vencimiento_pasado_del_endoso_no_molesta(self):
        """Un cheque de cartera vencido se puede endosar: no es error."""
        cartera = leer_cartera([{
            "DOCUMENTOFISICOID": 1, "NUMERO": "12345", "NROCHEQUEELECTRONICO": "12345",
            "BANCO": "BANCO MACRO S.A.", "TERCERO": "X", "CUITLIBRADOR": "30-1-7",
            "FECHAEMISION": "01-01-2025", "FECHAVENCIMIENTO": "18-01-2025",
            "IMPORTEMONTRANSACCION": "1000000", "EMPRESA": "CIMALCO NEUQUEN S.A.",
        }])
        proveedor = self._proveedor("Endoso 12345", "1000000")
        pago = armar(proveedor, proveedor.tramos, Decimal("0"), cartera, MAPA_BANCOS, 1, HOY)
        assert pago.endosos[0].fecha_vencimiento == date(2025, 1, 18)
