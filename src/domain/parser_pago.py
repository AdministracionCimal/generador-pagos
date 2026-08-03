import re
from datetime import date
from difflib import SequenceMatcher


_RE_FECHA = re.compile(r"(\d{1,2})/(\d{1,2})")

# Variantes exactas válidas para «transferencia»
_TRANSFERENCIA_EXACTAS = {
    "transferencia",
    "transferencia interbancaria",
    "transf",
    "transf.",
}
# Similitud mínima para aceptar typos como «tranferencia», «transferensia», etc.
# El gap es grande: typos reales caen en 0.83-0.98; términos no relacionados
# («tarjeta», «efectivo», «cheque») quedan por debajo de 0.40. 0.80 cubre
# typos múltiples sin riesgo de falsos positivos.
_TRANSFERENCIA_THRESHOLD = 0.80


def parsear_slots_fecha(
    texto: str,
    anio: int | None = None,
    fecha_emision: date | None = None,
) -> list[tuple[str, date | None]]:
    """Un "slot" por cada `dd/mm` del texto, en orden y sin descartar nada.

    `"Ch 31/02 - 10/06"` -> `[("31/02", None), ("10/06", date(...))]`

    El slot con `None` es una fecha que el usuario escribió mal (`31/02` no
    existe). Antes se descartaba, así que ese cheque desaparecía y el importe
    quedaba concentrado en los demás sin que nadie se enterara. Conservarlo
    permite emitirlo con fecha provisoria y pedirle al usuario que la corrija.
    """
    ref = fecha_emision or date.today()
    if anio is None:
        anio = ref.year

    slots: list[tuple[str, date | None]] = []
    for m in _RE_FECHA.finditer(texto or ""):
        dia, mes = int(m.group(1)), int(m.group(2))
        try:
            d = date(anio, mes, dia)
        except ValueError:
            slots.append((m.group(0), None))
            continue
        # Si la fecha cae antes de la emisión, probablemente es del año siguiente
        if fecha_emision is not None and d < fecha_emision:
            try:
                d = date(anio + 1, mes, dia)
            except ValueError:
                pass
        slots.append((m.group(0), d))
    return slots


def parsear_fechas_col_l(
    texto: str,
    anio: int | None = None,
    fecha_emision: date | None = None,
) -> list[date]:
    """
    "Ch 08/05 - 10/05 - 11/05 - 12/05" -> [date(2026,5,8), date(2026,5,10), ...]
    Retorna [] si el texto no contiene fechas (ej. "transferencia").

    Sólo las fechas válidas. Para fraccionar cheques usar `parsear_slots_fecha`,
    que además conserva las inválidas.
    """
    return [
        d for _, d in parsear_slots_fecha(texto, anio, fecha_emision)
        if d is not None
    ]


def fechas_descartadas(texto: str, anio: int | None = None) -> list[str]:
    """Tokens `dd/mm` del texto que no existen como fecha (ej. `31/02`).

    `parsear_fechas_col_l` los ignora, así que el proveedor terminaba con un
    cheque menos sin que nadie se enterara. Esto permite avisarlo al cargar.
    """
    return [
        token for token, fecha in parsear_slots_fecha(texto, anio)
        if fecha is None
    ]


def es_cheque(texto: str) -> bool:
    t = (texto or "").strip().lower()
    return bool(re.search(r"\bch\s*\d", t))


def _similitud_transferencia(texto: str) -> float:
    t = (texto or "").strip().lower()
    if not t:
        return 0.0
    return SequenceMatcher(None, t, "transferencia").ratio()


def es_transferencia(texto: str) -> bool:
    """True si es transferencia exacta o un typo cercano (ej. «tranferencia»)."""
    t = (texto or "").strip().lower()
    if t in _TRANSFERENCIA_EXACTAS:
        return True
    return _similitud_transferencia(t) >= _TRANSFERENCIA_THRESHOLD


def transferencia_con_typo(texto: str) -> bool:
    """True si el texto se interpretó como transferencia pero está mal escrito.
    Útil para avisar al usuario que corrija la ortografía en el Excel."""
    t = (texto or "").strip().lower()
    if not t or t in _TRANSFERENCIA_EXACTAS:
        return False
    return _similitud_transferencia(t) >= _TRANSFERENCIA_THRESHOLD
