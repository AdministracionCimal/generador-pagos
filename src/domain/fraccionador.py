from dataclasses import replace as _dc_replace
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from .models import ChequeEmitido, ItemFactura
from .parser_pago import parsear_fechas_col_l

_DOCS_UN_CHEQUE = {"movfondos", "nccpra", "ndcpra"}
_DOCS_CREDITO   = {"pago"}   # saldo a favor: no genera cheque, descuenta del total


def _es_un_cheque(documento: str) -> bool:
    doc = documento.strip().split(" - ")[0].lower().replace(" ", "")
    return any(doc.startswith(p) for p in _DOCS_UN_CHEQUE)


def _es_credito(documento: str) -> bool:
    doc = documento.strip().split(" - ")[0].lower().replace(" ", "")
    return any(doc.startswith(p) for p in _DOCS_CREDITO)


def fraccionar_item(
    item: ItemFactura,
    numero_desde: int,
    fecha_emision: date,
    anio: int | None = None,
) -> tuple[list[ChequeEmitido], int]:
    """
    Devuelve (cheques, proximo_numero).
    Para MOVFONDOS/NCCPRA/NDCPRA: 1 cheque por importe completo.
    Para FC: N cheques según fechas parseadas de col L.
    """
    if _es_un_cheque(item.documento):
        fechas = parsear_fechas_col_l(item.modalidad_pago, anio=anio, fecha_emision=fecha_emision)
        fecha_vto = fechas[0] if fechas else (item.fecha_vto or fecha_emision)
        cheque = ChequeEmitido(
            numero=str(numero_desde),
            importe=item.importe,
            fecha_emision=fecha_emision,
            fecha_vencimiento=fecha_vto,
        )
        return [cheque], numero_desde + 1

    fechas = parsear_fechas_col_l(item.modalidad_pago, anio=anio, fecha_emision=fecha_emision)
    if not fechas:
        # fallback: un cheque con fecha_vto
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
    suma_base = importe_base * n
    diferencia = item.importe - suma_base  # centavos de ajuste

    cheques = []
    for i, fecha_vto in enumerate(fechas):
        imp = importe_base
        if i == n - 1:
            imp = importe_base + diferencia
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
    Si todos los FCs del proveedor comparten exactamente las mismas fechas en col L,
    emite N cheques sobre el TOTAL de todos los FCs (no N cheques por cada FC).
    Los ítems de tipo MOVFONDOS/NCCPRA/NDCPRA siempre van con 1 cheque c/u.
    """
    items_credito   = [i for i in items if     _es_credito(i.documento)]
    items_fc        = [i for i in items if not _es_un_cheque(i.documento) and not _es_credito(i.documento)]
    items_un_cheque = [i for i in items if     _es_un_cheque(i.documento)]

    # Crédito total (PAGO -): ya negativo, reduce el bruto antes de dividir cheques
    credito_total = sum(i.importe for i in items_credito)

    todos: list[ChequeEmitido] = []
    siguiente = numero_desde

    # ── FCs ────────────────────────────────────────────────────────────────
    if items_fc:
        fechas_por_item = [
            parsear_fechas_col_l(i.modalidad_pago, anio=anio, fecha_emision=fecha_emision)
            for i in items_fc
        ]
        # ¿Todas las FCs tienen exactamente las mismas fechas?
        claves = {tuple(f.isoformat() for f in fs) for fs in fechas_por_item}
        consolidar = len(claves) == 1 and all(len(fs) > 0 for fs in fechas_por_item)

        if consolidar and len(items_fc) > 1:
            # Un único set de N cheques por el total neto (FCs − créditos PAGO -)
            fechas = fechas_por_item[0]
            total  = sum(i.importe for i in items_fc) + credito_total
            n      = len(fechas)
            base   = (total / n).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            ajuste = total - base * n          # diferencia de centavos al último
            for i, fecha_vto in enumerate(fechas):
                imp = base + ajuste if i == n - 1 else base
                todos.append(ChequeEmitido(
                    numero=str(siguiente + i),
                    importe=imp,
                    fecha_emision=fecha_emision,
                    fecha_vencimiento=fecha_vto,
                ))
            siguiente += n
        else:
            # Fechas distintas entre FCs → fraccionar cada una por separado.
            # Aplicar el crédito (PAGO -) al último FC antes de fraccionar,
            # de modo que el total de cheques = bruto − créditos.
            if credito_total != 0 and items_fc:
                ultimo_fc = _dc_replace(items_fc[-1], importe=items_fc[-1].importe + credito_total)
                items_fc_adj = items_fc[:-1] + [ultimo_fc]
            else:
                items_fc_adj = items_fc
            for item in items_fc_adj:
                cheques, siguiente = fraccionar_item(item, siguiente, fecha_emision, anio)
                todos.extend(cheques)

    # ── MOVFONDOS / NCCPRA / NDCPRA → 1 cheque c/u ────────────────────────
    for item in items_un_cheque:
        cheques, siguiente = fraccionar_item(item, siguiente, fecha_emision, anio)
        todos.extend(cheques)

    return todos, siguiente
