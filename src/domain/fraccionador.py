from dataclasses import replace as _dc_replace
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from .models import ChequeEmitido, ItemFactura
from .parser_pago import parsear_fechas_col_l


def _es_fc(documento: str) -> bool:
    return documento.strip().lower().startswith("fc -")


def fraccionar_item(
    item: ItemFactura,
    numero_desde: int,
    fecha_emision: date,
    anio: int | None = None,
) -> tuple[list[ChequeEmitido], int]:
    """
    Devuelve (cheques, proximo_numero).
    La cantidad de cheques sale de la columna «Forma de pago» (modalidad_pago).
    El tipo de documento (FC, MOVFONDOS, ND, etc.) NO determina cuántos cheques;
    cualquiera puede pagarse con 1 o N cheques según las fechas que traiga.
    Si no hay fechas parseables → 1 cheque (fallback con fecha_vto).
    """
    fechas = parsear_fechas_col_l(item.modalidad_pago, anio=anio, fecha_emision=fecha_emision)
    if not fechas:
        fecha_vto = item.fecha_vto or fecha_emision
        cheque = ChequeEmitido(
            numero=str(numero_desde),
            importe=item.importe,
            fecha_emision=fecha_emision,
            fecha_vencimiento=fecha_vto,
        )
        return [cheque], numero_desde + 1

    n = len(fechas)
    importe_base = (item.importe / n).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    suma_base    = importe_base * n
    diferencia   = item.importe - suma_base   # centavos de ajuste al último

    cheques = []
    for i, fecha_vto in enumerate(fechas):
        imp = importe_base + diferencia if i == n - 1 else importe_base
        cheques.append(ChequeEmitido(
            numero=str(numero_desde + i),
            importe=imp,
            fecha_emision=fecha_emision,
            fecha_vencimiento=fecha_vto,
        ))

    return cheques, numero_desde + n


def fraccionar_proveedor(
    items: list[ItemFactura],
    numero_desde: int,
    fecha_emision: date,
    anio: int | None = None,
) -> tuple[list[ChequeEmitido], int]:
    """
    Regla universal:
      - Crédito  (importe < 0): no genera cheque, reduce el bruto a pagar.
      - Pagable  (importe > 0): genera N cheques según su «Forma de pago».

    Si todas las FCs pagables comparten exactamente las mismas fechas,
    se consolida en un único set de N cheques por el total. El resto
    de pagables (MOVFONDOS, NDCPRA, etc.) se fracciona individualmente,
    cada uno respetando su propia «Forma de pago».
    """
    items_credito = [i for i in items if i.importe < Decimal("0")]
    items_pagable = [i for i in items if i.importe > Decimal("0")]
    items_fc      = [i for i in items_pagable if     _es_fc(i.documento)]
    items_otros   = [i for i in items_pagable if not _es_fc(i.documento)]

    # Crédito total (PAGO -, NC, MOVFONDOS positivo, etc.): ya negativo
    credito_total = sum(i.importe for i in items_credito)

    todos: list[ChequeEmitido] = []
    siguiente = numero_desde

    # ── FCs: consolidar si todas comparten las mismas fechas ──────────────
    if items_fc:
        fechas_por_item = [
            parsear_fechas_col_l(i.modalidad_pago, anio=anio, fecha_emision=fecha_emision)
            for i in items_fc
        ]
        claves = {tuple(f.isoformat() for f in fs) for fs in fechas_por_item}
        consolidar = len(claves) == 1 and all(len(fs) > 0 for fs in fechas_por_item)

        if consolidar and len(items_fc) > 1:
            # Un único set de N cheques por el total neto (FCs − créditos)
            fechas = fechas_por_item[0]
            total  = sum(i.importe for i in items_fc) + credito_total
            n      = len(fechas)
            base   = (total / n).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            ajuste = total - base * n
            for i, fecha_vto in enumerate(fechas):
                imp = base + ajuste if i == n - 1 else base
                todos.append(ChequeEmitido(
                    numero=str(siguiente + i),
                    importe=imp,
                    fecha_emision=fecha_emision,
                    fecha_vencimiento=fecha_vto,
                ))
            siguiente += n
            # Crédito ya consumido en el cálculo del total
            credito_aplicado = True
        else:
            # FCs con fechas distintas → fraccionar cada una por separado.
            # El crédito se aplica al último FC antes de fraccionar, así el
            # total de cheques = bruto − créditos.
            if credito_total != Decimal("0"):
                ultimo_fc = _dc_replace(
                    items_fc[-1],
                    importe=items_fc[-1].importe + credito_total,
                )
                items_fc_adj = items_fc[:-1] + [ultimo_fc]
                credito_aplicado = True
            else:
                items_fc_adj = items_fc
                credito_aplicado = False
            for item in items_fc_adj:
                cheques, siguiente = fraccionar_item(item, siguiente, fecha_emision, anio)
                todos.extend(cheques)
    else:
        credito_aplicado = False

    # ── Resto de pagables (MOVFONDOS, NDCPRA, etc.) ──────────────────────
    # Cada uno se fracciona según su propia «Forma de pago».
    # Si no hay FCs, el crédito se aplica al último pagable.
    if items_otros and not credito_aplicado and credito_total != Decimal("0"):
        ultimo = _dc_replace(
            items_otros[-1],
            importe=items_otros[-1].importe + credito_total,
        )
        items_otros = items_otros[:-1] + [ultimo]

    for item in items_otros:
        cheques, siguiente = fraccionar_item(item, siguiente, fecha_emision, anio)
        todos.extend(cheques)

    return todos, siguiente
