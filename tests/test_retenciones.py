from decimal import Decimal

from src.domain.models import ItemFactura
from src.domain.retenciones import calcular_retenciones
from src.ui.preview_dialog import _retencion_label


def _item(documento: str, importe: str) -> ItemFactura:
    return ItemFactura(
        documento=documento,
        comprobante="A-0001-00000001",
        descripcion="",
        importe=Decimal(importe),
        fecha_vto=None,
        modalidad_pago="Transferencia",
    )


def test_retenciones_incluyen_acumulado_y_codigo_para_preview():
    percepciones = [{"RetencionCodigo": "EN-BS"}]
    ret_maestros = {
        "EN-BS": {
            "Nombre": "Enajenación Bs de Cambio",
            "RetencionTipoCodigo": "GAN_RET",
            "ImporteMinimoImponible": 0,
            "RetencionItems": [{
                "ImporteDesde": 0,
                "ImporteHasta": 999999999,
                "Porcentaje": 2,
                "ImporteFijo": 0,
            }],
        }
    }
    historico = {
        "EN-BS": {
            "isar_historico": Decimal("1000"),
            "ya_retenido": Decimal("50"),
            "nombre": "Enajenación Bs de Cambio",
            "nombre_tipo": "Retención de Ganancias",
        }
    }

    retenciones, _items = calcular_retenciones(
        percepciones,
        ret_maestros,
        [_item("FC - 21473", "10000.00")],
        ratios_fc={"FC - 21473": Decimal("0.5")},
        historico=historico,
    )

    assert len(retenciones) == 1
    ret = retenciones[0]
    assert ret["_nombre"] == "Enajenación Bs de Cambio"
    assert ret["_nombre_tipo"] == "Retención de Ganancias"
    assert ret["_codigo"] == "EN-BS"
    assert ret["ISARAcumulado"] == 6000.0
    assert ret["_isar_acumulado"] == 6000.0
    assert _retencion_label(ret) == "Retención de Ganancias - Enajenación Bs de Cambio"


def test_credito_pago_reduce_base_imponible():
    """El crédito (PAGO -) reduce la base imponible proporcionalmente antes de calcular retenciones."""
    percepciones = [{"RetencionCodigo": "GAN"}]
    ret_maestros = {
        "GAN": {
            "Nombre": "Ganancias",
            "RetencionTipoCodigo": "GAN_RET",
            "ImporteMinimoImponible": 0,
            "RetencionItems": [{"ImporteDesde": 0, "ImporteHasta": 999999999,
                                 "Porcentaje": 2, "ImporteFijo": 0}],
        }
    }

    # Bruto FC = 10000, crédito = -1000 → neto = 9000 → factor = 0.9
    # Base bruta = 10000 × ratio 1.0 = 10000
    # Base neta  = 10000 × 0.9 = 9000 → retención = 9000 × 2% = 180
    fc  = _item("FC - 100", "10000.00")
    pago = ItemFactura("PAGO - 999", "", "", Decimal("-1000.00"), None, "")

    retenciones, _ = calcular_retenciones(
        percepciones, ret_maestros, [fc, pago],
        ratios_fc={"FC - 100": Decimal("1.0")},
    )

    assert len(retenciones) == 1
    assert retenciones[0]["ISAR"] == Decimal("9000.00")
    assert retenciones[0]["Importe"] == Decimal("180.00")


def test_sin_credito_base_imponible_no_cambia():
    """Sin crédito, la base imponible es el bruto de FCs (comportamiento anterior)."""
    percepciones = [{"RetencionCodigo": "GAN"}]
    ret_maestros = {
        "GAN": {
            "Nombre": "Ganancias",
            "RetencionTipoCodigo": "GAN_RET",
            "ImporteMinimoImponible": 0,
            "RetencionItems": [{"ImporteDesde": 0, "ImporteHasta": 999999999,
                                 "Porcentaje": 2, "ImporteFijo": 0}],
        }
    }

    fc = _item("FC - 100", "10000.00")
    retenciones, _ = calcular_retenciones(
        percepciones, ret_maestros, [fc],
        ratios_fc={"FC - 100": Decimal("1.0")},
    )

    assert retenciones[0]["ISAR"] == Decimal("10000.00")
    assert retenciones[0]["Importe"] == Decimal("200.00")


def test_retenciones_sin_historico_usan_nombre_generico_consistente():
    percepciones = [{"RetencionCodigo": "LOC-OB"}]
    ret_maestros = {
        "LOC-OB": {
            "Nombre": "Locaciones de Obra y Servicios Inscriptos",
            "RetencionTipoCodigo": "GAN_RET",
            "ImporteMinimoImponible": 0,
            "RetencionItems": [{
                "ImporteDesde": 0,
                "ImporteHasta": 999999999,
                "Porcentaje": 2,
                "ImporteFijo": 0,
            }],
        }
    }

    retenciones, _items = calcular_retenciones(
        percepciones,
        ret_maestros,
        [_item("FC - 21473", "10000.00")],
        ratios_fc={"FC - 21473": Decimal("0.5")},
        historico={},
    )

    assert len(retenciones) == 1
    ret = retenciones[0]
    assert ret["_nombre"] == "Locaciones de Obra y Servicios Inscriptos"
    assert ret["_nombre_tipo"] == "Retención de Ganancias"
    assert _retencion_label(ret) == "Retención de Ganancias - Locaciones de Obra y Servicios Inscriptos"
