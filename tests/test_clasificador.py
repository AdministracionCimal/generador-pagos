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

    def test_cabecera_pago_se_conserva_como_credito(self):
        """PAGO - ya no se filtra: es un crédito que descuenta del total."""
        p = ProveedorTanda(cuit="123", nombre="TEST", items=[
            ItemFactura("PAGO - 13992", "", "", Decimal("100"), None, "Ch 08/05"),
            ItemFactura("FC - 21562", "", "", Decimal("100"), None, "Ch 08/05"),
        ])
        result = clasificar(p)
        # Ambos items se conservan
        assert len(result.items) == 2
        docs = {i.documento for i in result.items}
        assert "PAGO - 13992" in docs
        assert "FC - 21562" in docs
        # La modalidad se clasifica por el FC, no por el PAGO -
        assert result.modalidad == Modalidad.CHEQUE_PROPIO

    def test_pago_solo_sin_facturas_es_manual(self):
        """Solo PAGO - sin FCs → sin items facturables → MANUAL."""
        p = ProveedorTanda(cuit="123", nombre="TEST", items=[
            ItemFactura("PAGO - 13992", "", "", Decimal("100"), None, "transferencia"),
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
