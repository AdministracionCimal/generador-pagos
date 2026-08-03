"""Ningún cheque con fecha en alerta puede llegar al POST."""
from datetime import date, timedelta
from decimal import Decimal

from src.domain.alertas_cheque import (
    ALERTA_FECHA_INVALIDA,
    ALERTA_FUTURO_DIAS,
    ALERTA_MUY_FUTURA,
    ALERTA_VENCIDA,
    alerta_cheque,
    cheques_en_alerta,
    es_muy_futura,
    motivo_alerta,
)
from src.domain.models import ChequeEmitido, OpPago, ProveedorTanda

HOY = date(2026, 8, 3)


def _cheque(
    fecha_vto: date,
    origen_invalida: str = "",
    plazo_confirmado: bool = False,
) -> ChequeEmitido:
    return ChequeEmitido(
        numero="100",
        importe=Decimal("1000"),
        fecha_emision=HOY,
        fecha_vencimiento=fecha_vto,
        fecha_origen_invalida=origen_invalida,
        plazo_confirmado=plazo_confirmado,
    )


class TestMotivoAlerta:
    def test_diferido_en_rango_no_alerta(self):
        assert motivo_alerta(_cheque(HOY + timedelta(days=30)), HOY) is None

    def test_ayer(self):
        assert "anterior a hoy" in motivo_alerta(_cheque(HOY - timedelta(days=1)), HOY)

    def test_hoy_el_banco_no_lo_acepta(self):
        assert "de hoy" in motivo_alerta(_cheque(HOY), HOY)

    def test_manana_si(self):
        assert motivo_alerta(_cheque(HOY + timedelta(days=1)), HOY) is None

    def test_limite_exacto_de_180_dias_no_alerta(self):
        assert motivo_alerta(_cheque(HOY + timedelta(days=ALERTA_FUTURO_DIAS)), HOY) is None

    def test_un_dia_mas_alerta_e_informa_los_dias(self):
        motivo = motivo_alerta(_cheque(HOY + timedelta(days=ALERTA_FUTURO_DIAS + 1)), HOY)
        assert "181 días" in motivo
        assert "más de 180" in motivo

    def test_fecha_del_excel_invalida_alerta_aunque_la_provisoria_sea_valida(self):
        """El caso «Ch 31/02»: el cheque queda con fecha de respaldo válida, pero
        nadie la eligió — tiene que ir en alerta igual."""
        ch = _cheque(HOY + timedelta(days=30), origen_invalida="31/02")
        motivo = motivo_alerta(ch, HOY)
        assert motivo is not None
        assert "31/02" in motivo

    def test_corregir_la_fecha_limpia_la_alerta(self):
        ch = _cheque(HOY + timedelta(days=30), origen_invalida="31/02")
        ch.fecha_origen_invalida = ""      # lo que hace el diálogo al editar
        assert motivo_alerta(ch, HOY) is None


class TestConfirmacionDePlazoLargo:
    """Un cheque a 240 días puede ser correcto (la ley permite hasta 360), así que
    esta alerta —y sólo esta— se puede confirmar en vez de corregir."""

    def test_confirmar_levanta_la_alerta_de_plazo_largo(self):
        largo = _cheque(HOY + timedelta(days=240))
        assert alerta_cheque(largo, HOY)[0] == ALERTA_MUY_FUTURA

        largo.plazo_confirmado = True
        assert alerta_cheque(largo, HOY) is None

    def test_confirmar_no_levanta_una_fecha_vencida(self):
        vencido = _cheque(HOY - timedelta(days=1), plazo_confirmado=True)
        assert alerta_cheque(vencido, HOY)[0] == ALERTA_VENCIDA

    def test_confirmar_no_levanta_una_fecha_de_hoy(self):
        hoy = _cheque(HOY, plazo_confirmado=True)
        assert alerta_cheque(hoy, HOY)[0] == ALERTA_VENCIDA

    def test_confirmar_no_levanta_una_fecha_inexistente_del_excel(self):
        invalido = _cheque(
            HOY + timedelta(days=30), origen_invalida="31/02", plazo_confirmado=True
        )
        assert alerta_cheque(invalido, HOY)[0] == ALERTA_FECHA_INVALIDA

    def test_es_muy_futura_ignora_la_confirmacion(self):
        """Lo usa el diálogo para mostrar el check: si mirara la alerta, al
        confirmarla el check desaparecería y la alerta volvería."""
        largo = _cheque(HOY + timedelta(days=240), plazo_confirmado=True)
        assert es_muy_futura(largo, HOY)
        assert not es_muy_futura(_cheque(HOY + timedelta(days=30)), HOY)

    def test_confirmado_se_puede_enviar(self):
        op = OpPago(
            proveedor=ProveedorTanda(cuit="30111111117", nombre="ACME SA"),
            cheques=[_cheque(HOY + timedelta(days=240), plazo_confirmado=True)],
        )
        assert cheques_en_alerta([op], HOY) == []


class TestChequesEnAlerta:
    def _op(self, *cheques: ChequeEmitido) -> OpPago:
        return OpPago(
            proveedor=ProveedorTanda(cuit="30111111117", nombre="ACME SA"),
            cheques=list(cheques),
        )

    def test_sin_alertas_lista_vacia(self):
        ops = [self._op(_cheque(HOY + timedelta(days=10)))]
        assert cheques_en_alerta(ops, HOY) == []

    def test_devuelve_proveedor_numero_y_motivo(self):
        ops = [self._op(_cheque(HOY, origen_invalida=""), _cheque(HOY + timedelta(days=5)))]
        alertas = cheques_en_alerta(ops, HOY)
        assert len(alertas) == 1
        nombre, numero, motivo = alertas[0]
        assert (nombre, numero) == ("ACME SA", "100")
        assert "de hoy" in motivo

    def test_transferencias_sin_cheques_no_alertan(self):
        assert cheques_en_alerta([self._op()], HOY) == []
