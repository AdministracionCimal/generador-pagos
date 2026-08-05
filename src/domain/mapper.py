from decimal import Decimal

from .models import ChequeEmitido, ChequeEndosado, Modalidad, OpPago, ProveedorTanda

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


def _endoso_a_banco(endoso: ChequeEndosado, op: OpPago) -> dict:
    """Cheque de tercero que se entrega al proveedor.

    Finnegans lo identifica por `DocumentoFisicoID` (el de cartera) y el
    `BancoCodigo` es el del **librador**, no el nuestro. No lleva chequera: el
    cheque no sale de un talonario propio.
    """
    return {
        "OperacionBancariaCodigo": op.op_bancaria_endoso_codigo,
        "CuentaCodigo": op.cuenta_valores_codigo,
        "DebeHaber": -1,
        "ImporteMonTransaccion": float(endoso.importe),
        "MonedaCodigo": MONEDA_PES,
        "ImporteMonPrincipal": float(endoso.importe),
        "Descripcion": None,
        "DocumentoFisicoID": endoso.documento_fisico_id,
        "FechaDocumentoFisico": _fmt_fecha(endoso.fecha_emision),
        "FechaVencimientoDocumentoFisico": _fmt_fecha(endoso.fecha_vencimiento),
        "ChequeraCodigo": None,
        "BancoCodigo": endoso.banco_codigo,
        "NumeroDocumentoFisico": endoso.numero,
        "DimensionDistribucion": [],
    }


def _transferencia_a_banco(op: OpPago, importe: Decimal) -> dict:
    return {
        "OperacionBancariaCodigo": op.op_bancaria_transferencia_codigo,
        "CuentaCodigo": op.cuenta_banco_transferencia_codigo or op.cuenta_banco_codigo,
        "DebeHaber": -1,
        "ImporteMonTransaccion": float(importe),
        "MonedaCodigo": MONEDA_PES,
        "ImporteMonPrincipal": float(importe),
        "Descripcion": None,
        "DocumentoFisicoID": None,
        "FechaDocumentoFisico": _fmt_fecha(op.fecha),
        "FechaVencimientoDocumentoFisico": _fmt_fecha(op.fecha),
        "ChequeraCodigo": None,
        "BancoCodigo": op.banco_codigo,
        "NumeroDocumentoFisico": None,
        "DimensionDistribucion": [],
    }


def _item_a_ctacte(item, cuenta_proveedor: str) -> dict:
    # Créditos (PAGO -, NC, importe negativo): van como Haber → DebeHaber=-1, importe positivo.
    # Finnegans no acepta ImporteMonTransaccion negativo en CtaCte.
    es_credito = item.importe < 0
    return {
        "CuentaCodigo": cuenta_proveedor,
        "DebeHaber": -1 if es_credito else 1,
        "ImporteMonTransaccion": float(abs(item.importe)),
        "MonedaCodigo": MONEDA_PES,
        "ImporteMonPrincipal": float(abs(item.importe)),
        "Descripcion": item.comprobante,
        "AplicacionOrigen": item.documento,
        "DimensionDistribucion": [],
    }


from .empresa import codigo_limpio as _empresa_codigo_limpio


def armar_post(op: OpPago) -> dict:
    p = op.proveedor
    # Orden: endosos primero, después los cheques propios y por último la
    # transferencia — igual que en las OPs cargadas a mano en Finnegans.
    banco = [_endoso_a_banco(e, op) for e in op.endosos]
    banco += [_cheque_a_banco(ch, op) for ch in op.cheques]

    if op.importe_transferencia is not None:
        # Pago combinado: el importe ya viene repartido (y con la retención
        # descontada de este tramo si le correspondía).
        banco.append(_transferencia_a_banco(op, op.importe_transferencia))
    elif p.modalidad == Modalidad.TRANSFERENCIA and not op.cheques:
        # Banco = neto (lo que realmente sale del banco = total - retenciones)
        total_ret = sum((r.get("Importe") or Decimal("0")) for r in op.retenciones)
        banco = [_transferencia_a_banco(op, p.importe_total - total_ret)]

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
