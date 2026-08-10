from decimal import Decimal

from .forma_pago import CHEQUE, TRANSFERENCIA, motivo_invalido, parsear_tramos
from .models import Modalidad, ProveedorTanda
from .parser_pago import (
    es_cheque,
    es_transferencia,
    fechas_descartadas,
    transferencia_con_typo,
)

_DOCS_IGNORAR = {"op"}    # ya procesadas por Finnegans → se eliminan


def _es_ignorable(documento: str) -> bool:
    doc = (documento or "").strip().lower()
    return any(doc.startswith(p) for p in _DOCS_IGNORAR)


def clasificar(proveedor: ProveedorTanda) -> ProveedorTanda:
    # Eliminar solo OP -; los créditos (importe<0) se conservan en items
    proveedor.items = [i for i in proveedor.items if not _es_ignorable(i.documento)]

    # Clasificar basándose únicamente en los ítems pagables (importe positivo).
    # Crédito (saldo a favor) = importe negativo en convención interna.
    items_reales = [i for i in proveedor.items if i.importe > Decimal("0")]

    if not items_reales:
        proveedor.modalidad = Modalidad.MANUAL
        proveedor.motivo_manual = "Sin items facturables"
        return proveedor

    textos_l = [i.modalidad_pago for i in items_reales]

    # Detectar typos en «transferencia» — se aceptan pero se avisa al usuario
    typos = sorted({t for t in textos_l if transferencia_con_typo(t)})
    for txt in typos:
        proveedor.avisos.append(
            f"«{txt}» se interpretó como «transferencia» — revisá la ortografía en el Excel"
        )

    # Fechas inexistentes (ej. «Ch 31/02»): se descartan al fraccionar, así que
    # el proveedor sale con menos cheques de los que dice el Excel.
    fechas_malas = {
        (i.modalidad_pago, tuple(fechas_descartadas(i.modalidad_pago)))
        for i in items_reales
        if es_cheque(i.modalidad_pago)
    }
    for texto, invalidas in sorted(fechas_malas):
        if invalidas:
            proveedor.avisos.append(
                f"«{texto}»: {', '.join(invalidas)} no existe como fecha y se ignoró "
                f"— se van a emitir menos cheques de los previstos"
            )

    # Cada texto se parsea en tramos: «Ch 10/09 + transferencia 30%» son dos.
    tramos_por_texto = {t: parsear_tramos(t) for t in set(textos_l)}

    def _es_medio_simple(texto: str, tipo: str) -> bool:
        """Un único tramo del tipo pedido y sin porcentaje: el camino de siempre."""
        tramos = tramos_por_texto[texto]
        return len(tramos) == 1 and tramos[0].tipo == tipo and tramos[0].porcentaje is None

    if all(_es_medio_simple(t, CHEQUE) for t in textos_l):
        proveedor.modalidad = Modalidad.CHEQUE_PROPIO
        return proveedor

    if all(_es_medio_simple(t, TRANSFERENCIA) for t in textos_l):
        proveedor.modalidad = Modalidad.TRANSFERENCIA
        return proveedor

    def _es_medio_unico(texto: str) -> bool:
        """Un solo tramo y sin porcentaje, del tipo que sea."""
        tramos = tramos_por_texto[texto]
        return len(tramos) == 1 and tramos[0].porcentaje is None

    # Mezcla por factura: cada ítem indica UN medio y no todos coinciden (ej. una
    # factura por transferencia y otra en cheques). Acá no hay porcentajes que
    # repartir: cada factura se paga por su importe, con su medio.
    if all(_es_medio_unico(t) for t in textos_l):
        proveedor.modalidad = Modalidad.MIXTO
        return proveedor

    # Pago combinado: el reparto se hace sobre el total del proveedor, así que
    # todos los ítems pagables tienen que indicar la misma combinación.
    textos_unicos = {t for t in textos_l if t}
    if len(textos_unicos) == 1:
        texto = next(iter(textos_unicos))
        tramos = tramos_por_texto[texto]
        motivo = motivo_invalido(tramos)
        if motivo is None:
            proveedor.modalidad = Modalidad.COMBINADO
            proveedor.tramos = tramos
            return proveedor
        proveedor.modalidad = Modalidad.MANUAL
        proveedor.motivo_manual = f"«{texto}»: {motivo}"
        return proveedor

    proveedor.modalidad = Modalidad.MANUAL
    proveedor.motivo_manual = (
        f"Modalidad mixta o no soportada: {sorted(textos_unicos)}"
    )
    return proveedor
