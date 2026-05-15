import pytest

from src.domain.numeracion import secuencia_comprobantes, siguiente_comprobante


def test_siguiente_comprobante_incrementa_ultimo_tramo_numerico():
    assert siguiente_comprobante("OP-0004-00022001") == "OP-0004-00022002"


def test_secuencia_comprobantes_devuelve_los_siguientes_numeros():
    assert secuencia_comprobantes("OP-0004-00022001", 3) == [
        "OP-0004-00022002",
        "OP-0004-00022003",
        "OP-0004-00022004",
    ]


def test_siguiente_comprobante_falla_sin_tramo_numerico():
    with pytest.raises(ValueError):
        siguiente_comprobante("TE-OP")
