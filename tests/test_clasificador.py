from decimal import Decimal

from src.domain.models import ItemFactura, Modalidad, ProveedorTanda
from src.domain.clasificador import clasificar


def _proveedor(*col_l_values: str) -> ProveedorTanda:
    items = [
        ItemFactura(
            documento=f"FC - {i}",
            comprobante="",
            descripcion="",
            importe=Decimal("1000"),
            fecha_vto=None,
            modalidad_pago=col_l,
        )
        for i, col_l in enumerate(col_l_values)
    ]
    return ProveedorTanda(cuit="30718308786", nombre="TEST", items=items)


class TestClasificar:
    def test_todos_cheque(self):
        p = _proveedor("Ch 08/05 - 10/05", "Ch 15/05", "Ch 22/05")
        assert clasificar(p).modalidad == Modalidad.CHEQUE_PROPIO

    def test_todos_transferencia(self):
        p = _proveedor("transferencia", "transferencia")
        assert clasificar(p).modalidad == Modalidad.TRANSFERENCIA

    def test_mixto_es_manual(self):
        p = _proveedor("Ch 08/05", "transferencia")
        resultado = clasificar(p)
        assert resultado.modalidad == Modalidad.MANUAL
        assert "mixta" in resultado.motivo_manual.lower()

    def test_tarjeta_es_manual(self):
        p = _proveedor("Tarjeta de Crédito")
        assert clasificar(p).modalidad == Modalidad.MANUAL

    def test_sin_items_es_manual(self):
        p = ProveedorTanda(cuit="123", nombre="VACIO")
        assert clasificar(p).modalidad == Modalidad.MANUAL

    def test_credito_se_conserva_pero_no_clasifica(self):
        """Crédito (importe<0) se conserva en items pero no influye en modalidad."""
        p = ProveedorTanda(cuit="123", nombre="TEST", items=[
            # crédito: importe negativo (PAGO - viene positivo en Excel, dm_reader lo niega)
            ItemFactura("PAGO - 13992", "", "", Decimal("-100"), None, ""),
            ItemFactura("FC - 21562",   "", "", Decimal("100"),  None, "Ch 08/05"),
        ])
        result = clasificar(p)
        assert len(result.items) == 2
        # La modalidad se clasifica por el FC, no por el crédito
        assert result.modalidad == Modalidad.CHEQUE_PROPIO

    def test_solo_credito_sin_pagables_es_manual(self):
        """Si todos los ítems son créditos (importe<0) → sin pagables → MANUAL."""
        p = ProveedorTanda(cuit="123", nombre="TEST", items=[
            ItemFactura("PAGO - 13992", "", "", Decimal("-100"), None, ""),
        ])
        result = clasificar(p)
        assert result.modalidad == Modalidad.MANUAL
        assert result.motivo_manual == "Sin items facturables"

    def test_op_se_sigue_filtrando(self):
        """OP - sigue siendo ignorado (ya procesado en Finnegans)."""
        p = ProveedorTanda(cuit="123", nombre="TEST", items=[
            ItemFactura("OP - 99999", "", "", Decimal("500"), None, "transferencia"),
            ItemFactura("FC - 21562", "", "", Decimal("100"), None, "transferencia"),
        ])
        result = clasificar(p)
        assert len(result.items) == 1
        assert result.items[0].documento == "FC - 21562"

    def test_typo_transferencia_se_clasifica_y_avisa(self):
        """«Tranferencia» (mal escrita) se acepta como transferencia y agrega aviso."""
        p = ProveedorTanda(cuit="123", nombre="TEST", items=[
            ItemFactura("FC - 100", "", "", Decimal("1000"), None, "Tranferencia"),
        ])
        result = clasificar(p)
        assert result.modalidad == Modalidad.TRANSFERENCIA
        assert len(result.avisos) == 1
        assert "Tranferencia" in result.avisos[0]
        assert "transferencia" in result.avisos[0].lower()

    def test_transferencia_correcta_no_genera_aviso(self):
        p = ProveedorTanda(cuit="123", nombre="TEST", items=[
            ItemFactura("FC - 100", "", "", Decimal("1000"), None, "transferencia"),
        ])
        result = clasificar(p)
        assert result.modalidad == Modalidad.TRANSFERENCIA
        assert result.avisos == []
