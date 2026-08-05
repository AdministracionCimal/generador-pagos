from pathlib import Path

import pytest

from src.domain.models import Modalidad
from src.excel.dm_reader import leer_dm

FIXTURE = Path(__file__).parent / "fixtures" / "07.05.2025.xlsx"


@pytest.mark.skipif(not FIXTURE.exists(), reason="fixture no disponible")
class TestLeerDM:
    def setup_method(self):
        self.proveedores = leer_dm(FIXTURE)

    def test_detecta_proveedores(self):
        assert len(self.proveedores) > 0

    def test_cof_sas_presente(self):
        nombres = [p.nombre for p in self.proveedores]
        assert "PROVEEDOR 014 SA" in nombres

    def test_cof_tiene_tres_items(self):
        cof = next(p for p in self.proveedores if p.nombre == "PROVEEDOR 014 SA")
        assert len(cof.items) == 3

    def test_cof_clasificado_cheque(self):
        cof = next(p for p in self.proveedores if p.nombre == "PROVEEDOR 014 SA")
        assert cof.modalidad == Modalidad.CHEQUE_PROPIO

    def test_cof_importe_total(self):
        from decimal import Decimal
        cof = next(p for p in self.proveedores if p.nombre == "PROVEEDOR 014 SA")
        # Suma de los 3 documentos: 917918.65 + 917918.65 + 12039500
        assert cof.importe_total == Decimal("13875337.30")

    def test_items_tienen_aplicacion_origen(self):
        cof = next(p for p in self.proveedores if p.nombre == "PROVEEDOR 014 SA")
        documentos = {i.documento for i in cof.items}
        assert "FC - 21562" in documentos or any("FC" in d for d in documentos)

    def test_no_hay_items_pago_como_facturas(self):
        for p in self.proveedores:
            for item in p.items:
                assert not item.documento.lower().startswith("pago -")
                assert not item.documento.lower().startswith("op -")
