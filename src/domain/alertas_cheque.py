"""Reglas de validez del vencimiento de un cheque.

Viven en el dominio porque las usan dos lugares:

- `PreviewDialog`, para pintar la fila en naranja y deshabilitar el envío;
- `main_window`, que se niega a hacer el POST si queda alguna alerta sin corregir.

Si la regla viviera sólo en la UI, un cheque con fecha inválida podría llegar a
Finnegans por cualquier camino que no pase por el diálogo.
"""
from datetime import date, timedelta

# Umbral para flaggear cheques con fecha sospechosa hacia el futuro.
# Caso real: typo en el día (06/05 en lugar de 06/06) hace que el parser
# infiera año siguiente y el cheque salga a ~1 año en lugar de ~1 mes.
ALERTA_FUTURO_DIAS = 180

# Tipos de alerta. Las dos primeras son errores objetivos y bloquean siempre;
# la tercera es una sospecha (un cheque a 240 días puede ser correcto), así que
# el usuario la puede confirmar desde la pantalla previa.
ALERTA_FECHA_INVALIDA = "fecha_invalida"
ALERTA_VENCIDA        = "vencida"
ALERTA_MUY_FUTURA     = "muy_futura"


def es_muy_futura(cheque, hoy: date | None = None) -> bool:
    """True si el vencimiento pasa el umbral, esté confirmado o no.

    La pantalla previa la usa para decidir si muestra el check de confirmación:
    si preguntara por la alerta, al confirmarla el check desaparecería y el
    cheque volvería a quedar en alerta.
    """
    hoy = hoy or date.today()
    return cheque.fecha_vencimiento > hoy + timedelta(days=ALERTA_FUTURO_DIAS)


def alerta_cheque(cheque, hoy: date | None = None) -> tuple[str, str] | None:
    """`(tipo, motivo)` si el cheque no está listo para enviarse, o None.

    Un cheque tiene que ser diferido (mañana en adelante): el banco no acepta
    una fecha igual o anterior al día actual.
    """
    hoy = hoy or date.today()
    if getattr(cheque, "fecha_origen_invalida", ""):
        return (
            ALERTA_FECHA_INVALIDA,
            f"«{cheque.fecha_origen_invalida}» del Excel no existe como fecha "
            f"— elegí el vencimiento",
        )
    fecha = cheque.fecha_vencimiento
    if fecha < hoy:
        return (ALERTA_VENCIDA, "fecha anterior a hoy")
    if fecha == hoy:
        return (ALERTA_VENCIDA, "fecha de hoy (el banco solo acepta cheques diferidos)")
    if es_muy_futura(cheque, hoy):
        if getattr(cheque, "plazo_confirmado", False):
            return None
        dias = (fecha - hoy).days
        return (
            ALERTA_MUY_FUTURA,
            f"fecha a {dias} días (más de {ALERTA_FUTURO_DIAS})",
        )
    return None


def motivo_alerta(cheque, hoy: date | None = None) -> str | None:
    """Sólo el motivo, para pintar la fila y el tooltip."""
    alerta = alerta_cheque(cheque, hoy)
    return alerta[1] if alerta is not None else None


def cheques_en_alerta(ops, hoy: date | None = None) -> list[tuple[str, str, str]]:
    """`[(proveedor, número de cheque, motivo)]` de todo lo que no se puede enviar."""
    hoy = hoy or date.today()
    return [
        (op.proveedor.nombre, ch.numero, motivo)
        for op in ops
        for ch in op.cheques
        if (motivo := motivo_alerta(ch, hoy)) is not None
    ]
