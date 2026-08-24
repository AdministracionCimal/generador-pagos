"""Normalización y reconocimiento de la columna «Documento» del Excel.

El texto se copia de Finnegans (`FC - 21562`) y se usa para tres cosas:

1. aplicar el pago al documento correcto en el POST (`AplicacionOrigen`),
2. verificar contra `composicionSaldoProveedor` que el documento tenga saldo,
3. saber si es una factura (`FC`), que es la base de las retenciones.

Un guion sin espacios (`FC-21562`) o un espacio doble rompía (2) y (3) en
silencio: el proveedor desaparecía de la lista como "sin saldo", o se pagaba
sin calcular la retención. Por eso todas las comparaciones pasan por acá.
"""
import re

_RE_PREFIJO = re.compile(r"^([A-Z]+)\s*-\s*(.*)$")

# Identificación externa que graba el sistema que carga facturas:
# `<CUIT>-<LETRA>-<PTO VENTA>-<NÚMERO>`. El CUIT puede venir con guiones, con
# puntos o pelado según quién lo escriba, y las tres formas son el mismo
# comprobante. Se canoniza a 11 dígitos para no depender de eso: pedirle al otro
# sistema que lo mande siempre igual sería apoyar el cruce en una convención que
# nadie valida.
_RE_ID_EXTERNA = re.compile(
    r"^(\d{2})[-.\s]?(\d{8})[-.\s]?(\d)-([A-Z])-(\d{4})-(\d{8})$"
)


def _canonizar_id_externa(texto: str) -> str | None:
    """`«20-31314441-1-A-0002-00000196»` → `«20313144411-A-0002-00000196»`."""
    match = _RE_ID_EXTERNA.match(texto)
    if match is None:
        return None
    cuit = f"{match.group(1)}{match.group(2)}{match.group(3)}"
    return f"{cuit}-{match.group(4)}-{match.group(5)}-{match.group(6)}"


def normalizar(documento: str) -> str:
    """Forma canónica para comparar: `" fc -21562 "` → `"FC - 21562"`."""
    texto = " ".join(str(documento or "").split()).upper()
    externa = _canonizar_id_externa(texto)
    if externa is not None:
        return externa
    match = _RE_PREFIJO.match(texto)
    if not match:
        return texto
    return f"{match.group(1)} - {match.group(2).strip()}"


def tiene_prefijo(documento: str, prefijo: str) -> bool:
    """True si el documento es de ese tipo, sin importar el espaciado del guion."""
    return normalizar(documento).startswith(f"{prefijo.upper()} - ")


def es_fc(documento: str) -> bool:
    """Factura de compra: única base de las retenciones de Ganancias."""
    return tiene_prefijo(documento, "FC")


def es_pago(documento: str) -> bool:
    """Crédito ya aplicado en Finnegans: no figura con saldo pendiente, pero
    tiene que viajar en el POST para descontar del total."""
    return tiene_prefijo(documento, "PAGO")


def id_externa(cuit: str, comprobante: str) -> str:
    """Reconstruye la `IdentificacionExterna` que graba el sistema de carga.

    `GET /facturaCompra/{clave}` resuelve por ese campo, **no** por el documento
    interno. Para lo que carga Finnegans los dos coinciden y no se nota; para lo
    que carga el otro sistema, `FC - 22219` devuelve 404 y hay que armar
    `<CUIT>-<comprobante>`. Sin eso el ratio gravado/total queda sin resolver, se
    asume 100% gravado y la retención sale de más.
    """
    digitos = re.sub(r"[^0-9]", "", str(cuit or ""))
    comp = " ".join(str(comprobante or "").split()).upper()
    if not digitos or not comp:
        return ""
    return f"{digitos}-{comp}"


# ── cruce contra composicionSaldoProveedor ────────────────────────────────────
#
# El reporte identifica la misma factura de tres formas y **no son intercambiables**:
#
#   DOCUMENTO             'FC - 22219'                  interno de Finnegans
#   COMPROBANTE           'A-0002-00000196'             letra-punto de venta-número
#   IDENTIFICACIONEXTERNA lo que grabó quien la cargó
#
# Hasta agosto 2026 `IDENTIFICACIONEXTERNA` venía igual a `DOCUMENTO` y el cruce se
# hacía sólo contra ella. Al empezar a cargarse facturas desde otro sistema, ese campo
# pasó a traer `<CUIT>-<LETRA>-<PTOVTA>-<NÚMERO>` (`20313144411-A-0002-00000196`), que no
# matchea con nada del Excel: la factura se daba por «sin saldo» y **se omitía del pago
# sin avisar**. Por eso ahora se indexan las tres claves y alcanza con que pegue una.
_CAMPOS_CLAVE = ("DOCUMENTO", "IDENTIFICACIONEXTERNA", "COMPROBANTE")


def claves_de_fila(fila: dict) -> set[str]:
    """Identificadores normalizados de una fila de `composicionSaldoProveedor`."""
    return {
        normalizar(fila.get(campo))
        for campo in _CAMPOS_CLAVE
        if str(fila.get(campo) or "").strip()
    }


def claves_pendientes(filas: list[dict]) -> dict[str, str]:
    """`{clave normalizada: IdentificacionExterna}` de lo que tiene saldo.

    Se guarda la identificación externa **tal cual la devuelve el ERP** porque es
    la que hay que mandar en `AplicacionOrigen`: ver `aplicacion_para()`. Las
    filas en cero no entran: son las ya canceladas.
    """
    indice: dict[str, str] = {}
    for fila in filas:
        try:
            importe = float(fila.get("IMPORTEMONTRAN", 0) or 0)
        except (TypeError, ValueError):
            importe = 0.0
        if importe == 0:
            continue
        externa = str(fila.get("IDENTIFICACIONEXTERNA") or "").strip()
        for clave in claves_de_fila(fila):
            indice.setdefault(clave, externa)
    return indice


def _candidatos(documento: str, comprobante: str = "") -> set[str]:
    """Las dos columnas del Excel, normalizadas, para buscar en el índice."""
    claves = {normalizar(documento)}
    if comprobante:
        claves.add(normalizar(comprobante))
    return claves


def figura_con_saldo(pendientes, documento: str, comprobante: str = "") -> bool:
    """True si el ítem del Excel se corresponde con alguna fila con saldo.

    Se prueban las dos columnas que trae el Excel («Documento» y «Comprobante»)
    porque cuál de las dos coincide depende de quién cargó la factura.
    """
    return any(clave in pendientes for clave in _candidatos(documento, comprobante))


def aplicacion_para(pendientes, documento: str, comprobante: str = "") -> str:
    """Identificador con el que Finnegans aplica el pago a la factura.

    `AplicacionOrigen` resuelve por `IdentificacionExterna`, **no** por el
    documento interno. Verificado contra el ERP: con `FC - 22219` la OP se crea
    con status 200 pero **no queda aplicada** — Finnegans lo trata igual que a un
    documento inexistente, y la factura sigue mostrando saldo (con lo cual el
    control de saldos la volvería a ofrecer para pagar).

    Para lo que carga Finnegans la identificación externa es el propio
    `FC - 21562`, así que el valor no cambia. Si no se pudo consultar el saldo,
    se cae al documento: es lo que se mandaba antes.
    """
    if isinstance(pendientes, dict):
        for clave in _candidatos(documento, comprobante):
            externa = pendientes.get(clave)
            if externa:
                return externa
    return documento
