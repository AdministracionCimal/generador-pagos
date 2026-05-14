from .models import Modalidad, ProveedorTanda
from .parser_pago import es_cheque, es_transferencia

_DOCS_NO_PAGO = {"pago", "op"}  # prefijos que son cabeceras, no facturas


def _es_item_facturable(documento: str) -> bool:
    doc = (documento or "").strip().lower()
    return not any(doc.startswith(p) for p in _DOCS_NO_PAGO)


def clasificar(proveedor: ProveedorTanda) -> ProveedorTanda:
    items_reales = [i for i in proveedor.items if _es_item_facturable(i.documento)]
    proveedor.items = items_reales

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
        modalidades_distintas = {t for t in textos_l if t}
        proveedor.motivo_manual = f"Modalidad mixta o no soportada: {modalidades_distintas}"

    return proveedor
