from decimal import Decimal

from .models import ChequeEmitido, Modalidad, OpPago, ProveedorTanda

MONEDA_PES = "PES"


def _fmt_fecha(d) -> str:
    return d.strftime("%Y-%m-%d") if d else ""


def _cheque_a_banco(ch: ChequeEmitido, op: OpPago) -> dict:
    return {
        "OperacionBancariaCodigo": op.op_bancaria_cheque_codigo,
        "CuentaCodigo": op.cuenta_banco_codigo,
        "DebeHaber": -1,
        "ImporteMonTransaccion": float(ch.importe),
        "MonedaCodigo": MONEDA_PES,
        "ImporteMonPrincipal": float(ch.importe),
        "Descripcion": None,
        "DocumentoFisicoID": None,
        "FechaDocumentoFisico": _fmt_fecha(ch.fecha_emision),
        "FechaVencimientoDocumentoFisico": _fmt_fecha(ch.fecha_vencimiento),
        "ChequeraCodigo": op.chequera_codigo,
        "BancoCodigo": op.banco_codigo,
        "NumeroDocumentoFisico": ch.numero,
        "DimensionDistribucion": [],
    }


def _item_a_ctacte(item, cuenta_proveedor: str) -> dict:
    return {
        "CuentaCodigo": cuenta_proveedor,
        "DebeHaber": 1,
        "ImporteMonTransaccion": float(item.importe),
        "MonedaCodigo": MONEDA_PES,
        "ImporteMonPrincipal": float(item.importe),
        "Descripcion": item.comprobante,
        "AplicacionOrigen": item.documento,
        "DimensionDistribucion": [],
    }


def _empresa_codigo_limpio(cod: str) -> str:
    """Quita el prefijo «EMPRESA_» que devuelve /empresa/list (ID interno).
    El POST de OPs requiere el código de negocio sin prefijo (ej. «EMPRE01»)."""
    return cod.removeprefix("EMPRESA_") if isinstance(cod, str) else cod


def armar_post(op: OpPago) -> dict:
    p = op.proveedor
    banco = [_cheque_a_banco(ch, op) for ch in op.cheques]

    if p.modalidad == Modalidad.TRANSFERENCIA and not op.cheques:
        # Banco = neto (lo que realmente sale del banco = total - retenciones)
        total_ret = sum((r.get("Importe") or Decimal("0")) for r in op.retenciones)
        total_neto = p.importe_total - total_ret
        banco = [{
            "OperacionBancariaCodigo": op.op_bancaria_transferencia_codigo,
            "CuentaCodigo": op.cuenta_banco_codigo,
            "DebeHaber": -1,
            "ImporteMonTransaccion": float(total_neto),
            "MonedaCodigo": MONEDA_PES,
            "ImporteMonPrincipal": float(total_neto),
            "Descripcion": None,
            "DocumentoFisicoID": None,
            "FechaDocumentoFisico": _fmt_fecha(op.fecha),
            "FechaVencimientoDocumentoFisico": _fmt_fecha(op.fecha),
            "ChequeraCodigo": None,
            "BancoCodigo": op.banco_codigo,
            "NumeroDocumentoFisico": None,
            "DimensionDistribucion": [],
        }]

    cta_cte = [_item_a_ctacte(i, op.cuenta_proveedor_codigo) for i in p.items]

    return {
        "IdentificacionExterna": "",
        "EmpresaCodigo": _empresa_codigo_limpio(op.empresa_codigo),
        "NumeroComprobante": "",
        "Proveedor": p.cuit,
        "TransaccionTipoCodigo": "OPERTESORERIA",
        "TransaccionSubtipoCodigo": "PAGO",
        "Fecha": _fmt_fecha(op.fecha),
        "Nombre": "",
        "DiferenciaCambio": 0,
        "UsaCotizacionOrigen": 1,
        "Descripcion": "",
        "CajaCodigo": None,
        "Banco": banco,
        "Efectivo": [],
        "Otros": [],
        "Retencion": [
            {
                **{
                    k: (float(v) if isinstance(v, Decimal) else v)
                    for k, v in r.items()
                    if not k.startswith("_")
                },
                "Fecha": _fmt_fecha(op.fecha),
            }
            for r in op.retenciones
        ],
        "OperacionTesoreriaCotizaciones": [
            {"MonedaCodigo": MONEDA_PES, "Cotizacion": 1},
            {"MonedaCodigo": "DOL", "Cotizacion": float(op.cotizacion_dolar)},
        ],
        "CtaCte": cta_cte,
        "ImportacionEcheq": False,
        "USR_ComboOC": None,
    }
