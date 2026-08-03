import re
from datetime import date
from difflib import SequenceMatcher


_RE_FECHA = re.compile(r"(\d{1,2})/(\d{1,2})")

# Palabra que identifica un cheque. El lookahead evita falsos positivos:
# «chequera 12» no es un cheque, y «echeq» tampoco (no hay límite de palabra
# antes de «cheq», así que ni entra).
_RE_PALABRA_CHEQUE = re.compile(r"\b(?:cheques|cheque|chq|ch)(?=\s|\.|\d|$)")
_RE_NUMERO_PEGADO  = re.compile(r"\s*\.?\s*\d")

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
    """True para «Ch 15/05», «ch15/05», «CHQ 15/05», «Cheque diferido 15/05».

    Hace falta la palabra **y** un número: la palabra sola («Cheque», sin fecha)
    queda en carga manual, porque no hay con qué armar el vencimiento.
    """
    t = (texto or "").strip().lower()
    match = _RE_PALABRA_CHEQUE.search(t)
    if match is None:
        return False
    # Número pegado a la palabra («ch15/05», «Ch 1») o una fecha en cualquier
    # parte del texto («Cheque diferido 15/05»).
    return bool(_RE_NUMERO_PEGADO.match(t[match.end():])) or bool(_RE_FECHA.search(t))


def _similitud_transferencia(texto: str) -> float:
    t = (texto or "").strip().lower()
    if not t:
        return 0.0
    return SequenceMatcher(None, t, "transferencia").ratio()


def _palabras(texto: str) -> list[str]:
    return [p.strip(",;:()") for p in texto.split()]


def _es_palabra_transferencia(palabra: str) -> bool:
    return (
        palabra in _TRANSFERENCIA_EXACTAS
        or _similitud_transferencia(palabra) >= _TRANSFERENCIA_THRESHOLD
    )


def es_transferencia(texto: str) -> bool:
    """True para «transferencia», typos cercanos («tranferencia») y frases que la
    contienen («transferencia bancaria», «Transferencia inmediata»).

    Se evalúa el texto completo y además palabra por palabra: si no fuera por
    esto, «transferencia bancaria» quedaba en 0.74 de similitud y caía en carga
    manual, aunque la palabra clave estuviera bien escrita.
    """
    t = (texto or "").strip().lower()
    if not t:
        return False
    if t in _TRANSFERENCIA_EXACTAS or _similitud_transferencia(t) >= _TRANSFERENCIA_THRESHOLD:
        return True
    # Texto ambiguo («cheque o transferencia»): no adivinar, que quede manual.
    if _RE_PALABRA_CHEQUE.search(t):
        return False
    return any(_es_palabra_transferencia(p) for p in _palabras(t))


def transferencia_con_typo(texto: str) -> bool:
    """True si el texto se interpretó como transferencia pero está mal escrito.
    Útil para avisar al usuario que corrija la ortografía en el Excel.

    Palabras de más no son un typo: «transferencia bancaria» está bien escrito.
    """
    t = (texto or "").strip().lower()
    if not t or t in _TRANSFERENCIA_EXACTAS or not es_transferencia(t):
        return False
    return not any(p in _TRANSFERENCIA_EXACTAS for p in _palabras(t))
