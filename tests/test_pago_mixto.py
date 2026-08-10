"""Mezcla por factura: cada una se paga con el medio que indica su fila.

Regla de deducciones (decisión del usuario): retenciones y créditos salen de la
transferencia y, si no alcanza o no hay, de los cheques. Nunca del endoso.
"""
from datetime import date
from decimal import Decimal

import pytest

from src.domain.bancos import mapa_por_nombre
from src.domain.cartera import leer_cartera
from src.domain.clasificador import clasificar
from src.domain.forma_pago import RepartoError
from src.domain.mapper import armar_post
from src.domain.models import ItemFactura, Modalidad, OpPago, ProveedorTanda
from src.domain.pago_combinado import armar_por_item

HOY = date(2026, 8, 7)
MAPA_BANCOS = mapa_por_nombre([{"codigo": "00285", "nombre": "BANCO MACRO S.A."}])


def _cartera(numero: str, importe: str) -> list:
    return leer_cartera([{
        "DOCUMENTOFISICOID": int(numero[-4:]), "NUMERO": numero,
        "NROCHEQUEELECTRONICO": numero, "BANCO": "BANCO MACRO S.A.",
        "TERCERO": "LIBRADOR SA", "CUITLIBRADOR": "30-11111111-7",
        "FECHAEMISION": "01-07-2026", "FECHAVENCIMIENTO": "01-09-2026",
        "IMPORTEMONTRANSACCION": importe, "EMPRESA": "CIMALCO NEUQUEN S.A.",
    }])


def _proveedor(*filas: tuple[str, str]) -> ProveedorTanda:
    """Cada fila es (importe, forma de pago). Importe negativo = crédito."""
    items = [
        ItemFactura(f"FC - {n}", f"A-{n}", "", Decimal(imp), None, forma)
        for n, (imp, forma) in enumerate(filas, 1)
    ]
    return clasificar(ProveedorTanda(cuit="30111111117", nombre="ACME SA", items=items))


def _armar(prov, retencion="0", cartera=None):
    return armar_por_item(
        prov, Decimal(retencion), cartera or [], MAPA_BANCOS,
        numero_desde=500, fecha_emision=HOY,
    )


class TestChequeMasTransferenciaPorFactura:
    def test_cada_factura_con_su_medio(self):
        prov = _proveedor(("1000000", "transferencia"), ("1000000", "Ch 10/09"))
        assert prov.modalidad == Modalidad.MIXTO

        pago = _armar(prov)
        assert pago.importe_transferencia == Decimal("1000000")
        assert [c.importe for c in pago.cheques] == [Decimal("1000000")]
        assert pago.total == Decimal("2000000")

    def test_la_transferencia_absorbe_la_retencion(self):
        """El ejemplo que definimos: transferencia 900.000 y cheque 1.000.000."""
        prov = _proveedor(("1000000", "transferencia"), ("1000000", "Ch 10/09"))
        pago = _armar(prov, retencion="100000")
        assert pago.importe_transferencia == Decimal("900000")
        assert sum(c.importe for c in pago.cheques) == Decimal("1000000")
        assert pago.total == Decimal("1900000")

    def test_cada_factura_conserva_sus_propias_fechas(self):
        prov = _proveedor(
            ("900000", "Ch 10/09 - 20/09 - 30/09"),
            ("500000", "Ch 15/10"),
            ("600000", "transferencia"),
        )
        pago = _armar(prov)
        assert [c.importe for c in pago.cheques] == [
            Decimal("300000"), Decimal("300000"), Decimal("300000"), Decimal("500000"),
        ]
        assert [c.fecha_vencimiento.strftime("%d/%m") for c in pago.cheques] == [
            "10/09", "20/09", "30/09", "15/10",
        ]
        assert pago.importe_transferencia == Decimal("600000")

    def test_numeracion_correlativa_entre_facturas(self):
        prov = _proveedor(("200000", "Ch 10/09 - 20/09"), ("100000", "Ch 15/10"))
        pago = _armar(prov)
        assert [c.numero for c in pago.cheques] == ["500", "501", "502"]
        assert pago.proximo_numero_cheque == 503

    def test_sin_transferencia_la_retencion_sale_de_los_cheques(self):
        prov = _proveedor(("600000", "Ch 10/09"), ("400000", "Ch 15/10"))
        # Con un solo medio el clasificador da CHEQUE_PROPIO; se fuerza MIXTO para
        # probar el reparto de deducciones de esta función.
        prov.modalidad = Modalidad.MIXTO
        pago = _armar(prov, retencion="100000")
        # Proporcional: 60% y 40% de la retención
        assert [c.importe for c in pago.cheques] == [Decimal("540000"), Decimal("360000")]
        assert pago.total == Decimal("900000")

    def test_los_creditos_tambien_salen_de_la_transferencia(self):
        prov = _proveedor(
            ("1000000", "transferencia"),
            ("1000000", "Ch 10/09"),
            ("-300000", ""),                 # PAGO/NC: crédito
        )
        pago = _armar(prov)
        assert pago.importe_transferencia == Decimal("700000")
        assert sum(c.importe for c in pago.cheques) == Decimal("1000000")
        assert pago.total == Decimal("1700000")

    def test_credito_mayor_que_la_transferencia_pasa_a_los_cheques(self):
        prov = _proveedor(
            ("200000", "transferencia"),
            ("1000000", "Ch 10/09"),
            ("-500000", ""),
        )
        pago = _armar(prov)
        assert pago.importe_transferencia == Decimal("0")
        assert sum(c.importe for c in pago.cheques) == Decimal("700000")

    def test_deducciones_mayores_que_el_pago_van_a_manual(self):
        prov = _proveedor(("100000", "transferencia"), ("100000", "Ch 10/09"))
        with pytest.raises(RepartoError, match="superan lo que se paga"):
            _armar(prov, retencion="500000")


class TestEndosoPorFactura:
    def test_endoso_que_cubre_su_factura(self):
        prov = _proveedor(("2000000", "Endoso 11139918"), ("500000", "Ch 10/09"))
        pago = _armar(prov, cartera=_cartera("11139918", "2000000"))
        assert [e.numero for e in pago.endosos] == ["11139918"]
        assert sum(c.importe for c in pago.cheques) == Decimal("500000")
        assert pago.total == Decimal("2500000")

    def test_endoso_que_no_cubre_su_factura(self):
        prov = _proveedor(("2000000", "Endoso 11139918"), ("500000", "Ch 10/09"))
        with pytest.raises(RepartoError, match="faltan"):
            _armar(prov, cartera=_cartera("11139918", "1800000"))

    def test_el_endoso_no_absorbe_la_retencion(self):
        prov = _proveedor(
            ("2000000", "Endoso 11139918"),
            ("1000000", "transferencia"),
        )
        pago = _armar(prov, retencion="100000", cartera=_cartera("11139918", "2000000"))
        assert pago.endosos[0].importe == Decimal("2000000")   # nominal intacto
        assert pago.importe_transferencia == Decimal("900000")

    def test_el_mismo_cheque_endosado_dos_veces_se_rechaza(self):
        prov = _proveedor(
            ("1000000", "Endoso 11139918"),
            ("1000000", "Endoso 11139918"),
        )
        with pytest.raises(RepartoError, match="más de una vez"):
            _armar(prov, cartera=_cartera("11139918", "1000000"))


class TestPostDeUnPagoMixto:
    def test_lleva_los_tres_tramos_con_su_cuenta(self):
        prov = _proveedor(
            ("2000000", "Endoso 11139918"),
            ("1000000", "Ch 10/09"),
            ("500000", "transferencia"),
        )
        pago = _armar(prov, cartera=_cartera("11139918", "2000000"))
        op = OpPago(
            proveedor=prov, cheques=pago.cheques, endosos=pago.endosos,
            importe_transferencia=pago.importe_transferencia,
            cuenta_banco_codigo="02.01.04.01.0009",
            cuenta_banco_transferencia_codigo="01.01.01.02.0006",
            fecha=HOY,
        )
        banco = armar_post(op)["Banco"]
        assert [(b["OperacionBancariaCodigo"], b["CuentaCodigo"]) for b in banco] == [
            ("CHENDOSADOS", "01.01.01.03.0001"),
            ("EMCHPROP", "02.01.04.01.0009"),
            ("TLote", "01.01.01.02.0006"),
        ]
        assert sum(b["ImporteMonTransaccion"] for b in banco) == 3500000.0

    def test_la_cta_cte_aplica_las_tres_facturas(self):
        prov = _proveedor(("1000000", "transferencia"), ("1000000", "Ch 10/09"))
        pago = _armar(prov)
        op = OpPago(proveedor=prov, cheques=pago.cheques,
                    importe_transferencia=pago.importe_transferencia, fecha=HOY)
        ctacte = armar_post(op)["CtaCte"]
        assert [c["AplicacionOrigen"] for c in ctacte] == ["FC - 1", "FC - 2"]
        assert all(c["DebeHaber"] == 1 for c in ctacte)
