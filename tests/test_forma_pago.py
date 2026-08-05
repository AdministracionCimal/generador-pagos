"""Gramática de «Forma de pago» con varios medios y su reparto de importes."""
import json
from decimal import Decimal
from pathlib import Path

import pytest

from src.domain.forma_pago import (
    CHEQUE,
    ENDOSO,
    TRANSFERENCIA,
    RepartoError,
    motivo_invalido,
    parsear_tramos,
    repartir,
)

FIXTURE_OP = Path(__file__).parent / "fixtures" / "response_OP-0004-00022502_endosos.json"


def _d(valor: str) -> Decimal:
    return Decimal(valor)


class TestParsearTramos:
    def test_un_solo_medio_sigue_funcionando(self):
        tramos = parsear_tramos("Ch 10/09 - 20/09")
        assert [t.tipo for t in tramos] == [CHEQUE]
        assert tramos[0].porcentaje is None
        assert tramos[0].fechas_texto == "Ch 10/09 - 20/09"

    def test_cheque_mas_transferencia_con_porcentaje(self):
        tramos = parsear_tramos("Ch 10/09 + transferencia 30%")
        assert [t.tipo for t in tramos] == [CHEQUE, TRANSFERENCIA]
        assert tramos[0].porcentaje is None
        assert tramos[1].porcentaje == 30

    def test_porcentaje_en_el_cheque(self):
        tramos = parsear_tramos("Ch 10/09 - 20/09 70% + transferencia 30%")
        assert tramos[0].porcentaje == 70
        # el % no se confunde con una fecha
        assert "70" not in tramos[0].fechas_texto

    def test_porcentaje_con_decimales_y_espacio(self):
        tramos = parsear_tramos("transferencia 33,5 % + Ch 10/09")
        assert tramos[0].porcentaje == Decimal("33.5")

    def test_endoso_con_un_cheque(self):
        tramos = parsear_tramos("Endoso 11139918 + Ch 10/09")
        assert [t.tipo for t in tramos] == [ENDOSO, CHEQUE]
        assert tramos[0].numeros_cheque == ["11139918"]

    def test_endoso_con_varios_cheques(self):
        tramos = parsear_tramos("Endosos 03744628 - 03744629 - 90000077 + transferencia")
        assert tramos[0].numeros_cheque == ["03744628", "03744629", "90000077"]
        assert tramos[1].tipo == TRANSFERENCIA

    def test_abreviatura_end(self):
        assert parsear_tramos("End 11139918")[0].tipo == ENDOSO

    def test_endoso_sin_numero_no_se_reconoce(self):
        assert parsear_tramos("Endoso") == []

    def test_texto_no_reconocido_se_ignora(self):
        assert parsear_tramos("efectivo") == []
        assert parsear_tramos("") == []

    def test_tramo_no_reconocido_no_arrastra_a_los_demas(self):
        tramos = parsear_tramos("Ch 10/09 + efectivo")
        assert [t.tipo for t in tramos] == [CHEQUE]


class TestMotivoInvalido:
    def test_combinacion_valida(self):
        assert motivo_invalido(parsear_tramos("Ch 10/09 + transferencia 30%")) is None

    def test_porcentajes_que_suman_cien(self):
        assert motivo_invalido(parsear_tramos("Ch 10/09 70% + transferencia 30%")) is None

    def test_porcentajes_que_no_suman_cien(self):
        motivo = motivo_invalido(parsear_tramos("Ch 10/09 60% + transferencia 30%"))
        assert "90% en lugar de 100%" in motivo

    def test_dos_tramos_sin_porcentaje_es_ambiguo(self):
        motivo = motivo_invalido(parsear_tramos("Ch 10/09 + transferencia"))
        assert "más de un tramo sin porcentaje" in motivo

    def test_tramos_repetidos_del_mismo_tipo(self):
        motivo = motivo_invalido(parsear_tramos("Ch 10/09 50% + Ch 20/10 50%"))
        assert "tramos de cheque" in motivo

    def test_solo_endosos_es_valido(self):
        """Los cheques endosados pueden cubrir exactamente el importe."""
        assert motivo_invalido(parsear_tramos("Endoso 111122 - 333344")) is None

    def test_sin_tramos(self):
        assert "no se reconoció" in motivo_invalido([])


class TestRepartir:
    def test_ejemplo_del_usuario(self):
        """«Ch 10/09 + transferencia 30%» sobre 1.000.000 con 50.000 de retención:
        la transferencia paga el 30% menos la retención (pagar menos ahora) y el
        cheque se queda con el resto."""
        partes = repartir(
            parsear_tramos("Ch 10/09 + transferencia 30%"),
            importe_a_pagar=_d("1000000"),
            retencion_total=_d("50000"),
        )
        por_tipo = {p.tramo.tipo: p for p in partes}
        assert por_tipo[TRANSFERENCIA].importe == _d("250000")
        assert por_tipo[TRANSFERENCIA].retencion == _d("50000")
        assert por_tipo[CHEQUE].importe == _d("700000")
        assert sum(p.importe for p in partes) == _d("950000")   # el neto

    def test_sin_transferencia_la_retencion_sale_del_cheque(self):
        partes = repartir(
            parsear_tramos("Endoso 111 + Ch 10/09"),
            importe_a_pagar=_d("1000000"),
            retencion_total=_d("50000"),
            importes_endoso={"111": _d("400000")},
        )
        por_tipo = {p.tramo.tipo: p for p in partes}
        assert por_tipo[ENDOSO].importe == _d("400000")      # nominal intacto
        assert por_tipo[ENDOSO].retencion == _d("0")
        assert por_tipo[CHEQUE].importe == _d("550000")
        assert sum(p.importe for p in partes) == _d("950000")

    def test_el_endoso_nunca_absorbe_la_retencion(self):
        with pytest.raises(RepartoError, match="sólo hay endosos"):
            repartir(
                parsear_tramos("Endoso 111"),
                importe_a_pagar=_d("1000000"),
                retencion_total=_d("50000"),
                importes_endoso={"111": _d("950000")},
            )

    def test_endosos_que_superan_el_neto_se_rechazan(self):
        """Saldo a favor: no se automatiza, va a carga manual con la diferencia."""
        with pytest.raises(RepartoError, match="a favor del proveedor"):
            repartir(
                parsear_tramos("Endoso 111 + Ch 10/09"),
                importe_a_pagar=_d("1000000"),
                retencion_total=_d("50000"),
                importes_endoso={"111": _d("960000")},
            )

    def test_endoso_que_no_esta_en_cartera(self):
        with pytest.raises(RepartoError, match="no se encontró en cartera"):
            repartir(
                parsear_tramos("Endoso 999 + Ch 10/09"),
                importe_a_pagar=_d("1000"),
                importes_endoso={"111": _d("500")},
            )

    def test_solo_endosos_que_no_cubren_el_total(self):
        """Saldo pendiente: tampoco se automatiza (Finnegans recalcula las
        retenciones al tocar el importe de la cuenta corriente)."""
        with pytest.raises(RepartoError, match="faltan"):
            repartir(
                parsear_tramos("Endoso 111"),
                importe_a_pagar=_d("1000"),
                importes_endoso={"111": _d("600")},
            )

    def test_solo_endosos_que_cubren_exacto(self):
        partes = repartir(
            parsear_tramos("Endoso 111 - 222"),
            importe_a_pagar=_d("1000"),
            importes_endoso={"111": _d("600"), "222": _d("400")},
        )
        assert len(partes) == 1
        assert partes[0].importe == _d("1000")

    def test_los_centavos_del_redondeo_van_al_resto(self):
        partes = repartir(
            parsear_tramos("Ch 10/09 + transferencia 33,33%"),
            importe_a_pagar=_d("1000.01"),
        )
        por_tipo = {p.tramo.tipo: p for p in partes}
        assert por_tipo[TRANSFERENCIA].importe == _d("333.30")   # 33,33% redondeado
        assert por_tipo[CHEQUE].importe == _d("666.71")          # absorbe el resto
        assert sum(p.importe for p in partes) == _d("1000.01")

    def test_retencion_que_no_entra_en_el_tramo(self):
        with pytest.raises(RepartoError, match="no entra en el tramo"):
            repartir(
                parsear_tramos("Ch 10/09 + transferencia 10%"),
                importe_a_pagar=_d("1000"),
                retencion_total=_d("500"),
            )

    def test_respeta_el_orden_escrito(self):
        tramos = parsear_tramos("Endoso 111 + transferencia 30% + Ch 10/09")
        partes = repartir(
            tramos,
            importe_a_pagar=_d("1000"),
            importes_endoso={"111": _d("200")},
        )
        assert [p.tramo.tipo for p in partes] == [ENDOSO, TRANSFERENCIA, CHEQUE]


class TestContraLaOpRealDeFinnegans:
    """La OP OP-0004-00022502 se cargó a mano en Finnegans con 3 endosos y 8
    cheques propios. El reparto de la app tiene que dar los mismos importes."""

    @pytest.fixture(scope="class")
    def op(self):
        return json.loads(FIXTURE_OP.read_text(encoding="utf-8"))

    def test_la_op_real_cierra_banco_igual_al_neto(self, op):
        debe = sum(Decimal(str(i["ImporteMonTransaccion"]))
                   for i in op["CtaCte"] if i["DebeHaber"] == 1)
        haber = sum(Decimal(str(i["ImporteMonTransaccion"]))
                    for i in op["CtaCte"] if i["DebeHaber"] == -1)
        retencion = sum(Decimal(str(r["Importe"])) for r in op["Retencion"])
        banco = sum(Decimal(str(b["ImporteMonTransaccion"])) for b in op["Banco"])
        # Finnegans: total del banco = (facturas − créditos) − retenciones
        assert banco == debe - haber - retencion

    def test_el_reparto_reproduce_los_importes_reales(self, op):
        endosos = [b for b in op["Banco"] if b["OperacionBancariaCodigo"] == "CHENDOSADOS"]
        propios = [b for b in op["Banco"] if b["OperacionBancariaCodigo"] == "EMCHPROP"]

        debe = sum(Decimal(str(i["ImporteMonTransaccion"]))
                   for i in op["CtaCte"] if i["DebeHaber"] == 1)
        haber = sum(Decimal(str(i["ImporteMonTransaccion"]))
                    for i in op["CtaCte"] if i["DebeHaber"] == -1)
        retencion = sum(Decimal(str(r["Importe"])) for r in op["Retencion"])

        importes_endoso = {
            b["NumeroDocumentoFisico"]: Decimal(str(b["ImporteMonTransaccion"]))
            for b in endosos
        }
        texto = "Endoso " + " - ".join(importes_endoso) + " + Ch " + " - ".join(
            b["FechaVencimientoDocumentoFisico"][8:10] + "/" +
            b["FechaVencimientoDocumentoFisico"][5:7] for b in propios
        )

        partes = repartir(
            parsear_tramos(texto),
            importe_a_pagar=debe - haber,
            retencion_total=retencion,
            importes_endoso=importes_endoso,
        )
        por_tipo = {p.tramo.tipo: p for p in partes}

        assert por_tipo[ENDOSO].importe == sum(importes_endoso.values())
        assert por_tipo[CHEQUE].importe == sum(
            Decimal(str(b["ImporteMonTransaccion"])) for b in propios
        )
        assert sum(p.importe for p in partes) == sum(
            Decimal(str(b["ImporteMonTransaccion"])) for b in op["Banco"]
        )
