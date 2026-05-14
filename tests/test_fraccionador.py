from datetime import date
from decimal import Decimal

import pytest

from src.domain.models import ItemFactura
from src.domain.fraccionador import fraccionar_item, fraccionar_proveedor


FECHA_EMISION = date(2026, 5, 8)


def _item(documento: str, importe: str, col_l: str) -> ItemFactura:
    return ItemFactura(
        documento=documento,
        comprobante="TEST",
        descripcion="",
        importe=Decimal(importe),
        fecha_vto=None,
        modalidad_pago=col_l,
    )


class TestFraccionarItem:
    def test_movfondos_un_cheque(self):
        item = _item("MOVFONDOS - 10845", "917918.65", "Ch 15/05")
        cheques, sig = fraccionar_item(item, numero_desde=73189907, fecha_emision=FECHA_EMISION, anio=2026)
        assert len(cheques) == 1
        assert cheques[0].importe == Decimal("917918.65")
        assert cheques[0].numero == "73189907"
        assert sig == 73189908

    def test_fc_seis_cheques(self):
        item = _item("FC - 21562", "12014792.88", "Ch 08/06 - 09/06 - 18/06 - 19/06 - 05/07 - 06/07")
        cheques, sig = fraccionar_item(item, numero_desde=100, fecha_emision=FECHA_EMISION, anio=2026)
        assert len(cheques) == 6
        assert sig == 106
        total = sum(c.importe for c in cheques)
        assert total == Decimal("12014792.88")

    def test_fc_ajuste_ultimo_centavo(self):
        # 10 / 3 no es exacto — el último cheque absorbe la diferencia
        item = _item("FC - 99999", "10.00", "Ch 01/06 - 02/06 - 03/06")
        cheques, _ = fraccionar_item(item, numero_desde=1, fecha_emision=FECHA_EMISION, anio=2026)
        assert len(cheques) == 3
        assert sum(c.importe for c in cheques) == Decimal("10.00")

    def test_nccpra_un_cheque(self):
        item = _item("NCCPRA - 609", "5000.00", "Ch 09/05")
        cheques, _ = fraccionar_item(item, numero_desde=1, fecha_emision=FECHA_EMISION, anio=2026)
        assert len(cheques) == 1

    def test_ndcpra_un_cheque(self):
        item = _item("NDCPRA - 240", "3000.00", "Ch 09/05")
        cheques, _ = fraccionar_item(item, numero_desde=1, fecha_emision=FECHA_EMISION, anio=2026)
        assert len(cheques) == 1


class TestFraccionarProveedor:
    def test_dos_movfondos_mas_fc(self):
        items = [
            _item("MOVFONDOS - 10845", "917918.65", "Ch 15/05"),
            _item("MOVFONDOS - 10846", "917918.65", "Ch 16/05"),
            _item("FC - 21562", "12014792.88", "Ch 08/06 - 09/06 - 18/06 - 19/06 - 05/07 - 06/07"),
        ]
        cheques, siguiente = fraccionar_proveedor(items, numero_desde=73189907, fecha_emision=FECHA_EMISION, anio=2026)
        assert len(cheques) == 8  # 1 + 1 + 6
        assert siguiente == 73189915
        total = sum(c.importe for c in cheques)
        assert total == Decimal("917918.65") + Decimal("917918.65") + Decimal("12014792.88")
