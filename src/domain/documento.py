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
