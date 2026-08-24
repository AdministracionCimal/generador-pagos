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


def normalizar(documento: str) -> str:
    """Forma canónica para comparar: `" fc -21562 "` → `"FC - 21562"`."""
    texto = " ".join(str(documento or "").split()).upper()
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


def claves_pendientes(filas: list[dict]) -> set[str]:
    """Índice de lo que tiene saldo. Las filas en cero no entran: son las ya canceladas."""
    claves: set[str] = set()
    for fila in filas:
        try:
            importe = float(fila.get("IMPORTEMONTRAN", 0) or 0)
        except (TypeError, ValueError):
            importe = 0.0
        if importe != 0:
            claves |= claves_de_fila(fila)
    return claves


def figura_con_saldo(pendientes: set[str], documento: str, comprobante: str = "") -> bool:
    """True si el ítem del Excel se corresponde con alguna fila con saldo.

    Se prueban las dos columnas que trae el Excel («Documento» y «Comprobante»)
    porque cuál de las dos coincide depende de quién cargó la factura.
    """
    candidatos = {normalizar(documento)}
    if comprobante:
        candidatos.add(normalizar(comprobante))
    return bool(candidatos & pendientes)
