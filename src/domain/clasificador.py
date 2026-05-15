from decimal import Decimal

from .models import Modalidad, ProveedorTanda
from .parser_pago import es_cheque, es_transferencia, transferencia_con_typo

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

    todos_cheque = all(es_cheque(t) for t in textos_l)
    todos_transf = all(es_transferencia(t) for t in textos_l)

    if todos_cheque:
        proveedor.modalidad = Modalidad.CHEQUE_PROPIO
    elif todos_transf:
        proveedor.modalidad = Modalidad.TRANSFERENCIA
    else:
        proveedor.modalidad = Modalidad.MANUAL
        modalidades_distintas = sorted({t for t in textos_l if t})
        proveedor.motivo_manual = f"Modalidad mixta o no soportada: {modalidades_distintas}"

    return proveedor
