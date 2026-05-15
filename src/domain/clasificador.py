from .models import Modalidad, ProveedorTanda
from .parser_pago import es_cheque, es_transferencia

_DOCS_IGNORAR = {"op"}    # ya procesadas por Finnegans → se eliminan
_DOCS_CREDITO = {"pago"}  # saldo a favor → se conservan pero no clasifican


def _es_ignorable(documento: str) -> bool:
    doc = (documento or "").strip().lower()
    return any(doc.startswith(p) for p in _DOCS_IGNORAR)


def _es_credito(documento: str) -> bool:
    doc = (documento or "").strip().lower()
    return any(doc.startswith(p) for p in _DOCS_CREDITO)


def clasificar(proveedor: ProveedorTanda) -> ProveedorTanda:
    # Eliminar solo OP -; los PAGO - (créditos) se conservan en items
    proveedor.items = [i for i in proveedor.items if not _es_ignorable(i.documento)]

    # Clasificar basándose únicamente en los ítems que no son créditos
    items_reales = [i for i in proveedor.items if not _es_credito(i.documento)]

    if not items_reales:
        proveedor.modalidad = Modalidad.MANUAL
        proveedor.motivo_manual = "Sin items facturables"
        return proveedor

    textos_l = [i.modalidad_pago for i in items_reales]

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
