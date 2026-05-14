"""
Cálculo de retenciones de Ganancias a partir del maestro de Finnegans.

Flujo:
  1. GET /proveedor/{cuit}                      → Percepciones[].RetencionCodigo
  2. GET /retencion/{code}                      → tramos + ImporteMinimoImponible
  3. GET /facturaCompra/{doc}                   → ratio gravado/total por FC
  4. GET /reports/analisisRetencion (opcional)  → ISAR + IMPORTE históricos del mes
  5. calcular_retenciones()                     → Retencion[] para el POST

Fórmula con acumulado (igual que el SP CalculoRetencionesModoBatchTesoreria):
  isar_acumulado   = isar_historico_mes + base_imponible_actual
  retencion_bruta  = escala(isar_acumulado)
  retencion_final  = max(0, retencion_bruta - ya_retenido_mes)
"""
from dataclasses import replace
from decimal import Decimal, ROUND_HALF_UP

from .models import ItemFactura


def _es_fc(documento: str) -> bool:
    return documento.strip().lower().startswith("fc -")


def calcular_importe_retencion(ret_data: dict, base_neto: Decimal) -> Decimal:
    """Aplica escala sobre la base acumulada. Retorna 0 si no supera el mínimo."""
    min_imp = Decimal(str(ret_data.get("ImporteMinimoImponible", 0)))
    if base_neto < min_imp:
        return Decimal("0")
    for item in ret_data.get("RetencionItems", []):
        desde = Decimal(str(item["ImporteDesde"]))
        hasta = Decimal(str(item["ImporteHasta"]))
        if desde <= base_neto <= hasta:
            pct  = Decimal(str(item["Porcentaje"]))
            fijo = Decimal(str(item.get("ImporteFijo", 0)))
            return ((base_neto - desde) * pct / 100 + fijo).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
    return Decimal("0")


def calcular_retenciones(
    percepciones: list[dict],
    ret_maestros: dict[str, dict],
    items: list[ItemFactura],
    ratios_fc: dict[str, Decimal] | None = None,
    historico: dict[str, dict] | None = None,
) -> tuple[list[dict], list[ItemFactura]]:
    """
    Retorna (retenciones_para_post, items_con_importes_netos).

    historico = {
        "GAN_RET": {
            "isar_historico": Decimal,   # ISAR acumulado en el mes (sin la op actual)
            "ya_retenido":    Decimal,   # Retenciones ya practicadas en el mes
            "nombre":         str,       # Nombre legible del tipo de retención
        },
        ...
    }
    Si historico es None o el código no está, se usa isar_historico=0 / ya_retenido=0
    (comportamiento previo — correcto para el primer pago del mes).
    """
    ratios_fc = ratios_fc or {}
    historico  = historico  or {}

    items_fc = [i for i in items if _es_fc(i.documento)]
    if not items_fc:
        return [], items

    # Base imponible = porción gravada de lo que se paga en esta OP
    base_imponible = sum(
        i.importe * Decimal(str(ratios_fc.get(i.documento, Decimal("1"))))
        for i in items_fc
    )
    if base_imponible <= Decimal("0"):
        return [], items

    retenciones_post: list[dict] = []
    total_ret = Decimal("0")

    for p in percepciones:
        codigo = p.get("RetencionCodigo")
        if not codigo or codigo not in ret_maestros:
            continue

        hist            = historico.get(codigo, {})
        isar_historico  = Decimal(str(hist.get("isar_historico", 0)))
        ya_retenido     = Decimal(str(hist.get("ya_retenido",    0)))
        nombre_tipo     = hist.get("nombre", codigo)

        isar_acumulado  = isar_historico + base_imponible
        retencion_bruta = calcular_importe_retencion(ret_maestros[codigo], isar_acumulado)
        importe         = max(Decimal("0"), retencion_bruta - ya_retenido)

        if importe > Decimal("0"):
            retenciones_post.append({
                "RetencionCodigo": codigo,
                "Importe":         float(importe),
                "ISAR":            float(base_imponible),   # base imponible de esta OP
                "ISARAcumulado":   float(isar_acumulado),   # histórico del mes + esta OP
                # Campos extra para el preview (no van al POST de Finnegans)
                "_nombre":         nombre_tipo,
                "_isar_historico": float(isar_historico),
                "_ya_retenido":    float(ya_retenido),
            })
            total_ret += importe

    if total_ret == Decimal("0"):
        return retenciones_post, items

    # Distribuir la retención proporcionalmente entre los ítems FC
    total_fc_bruto = sum(i.importe for i in items_fc)
    ret_distribuida = Decimal("0")
    fc_count      = len(items_fc)
    fc_procesados = 0
    items_resultado: list[ItemFactura] = []

    for item in items:
        if not _es_fc(item.documento):
            items_resultado.append(item)
            continue
        fc_procesados += 1
        if fc_procesados == fc_count:
            descuento = total_ret - ret_distribuida
        else:
            proporcion = item.importe / total_fc_bruto
            descuento  = (total_ret * proporcion).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            ret_distribuida += descuento
        items_resultado.append(replace(item, importe=item.importe - descuento))

    return retenciones_post, items_resultado
