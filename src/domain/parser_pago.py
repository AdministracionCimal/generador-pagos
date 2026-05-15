import re
from datetime import date


_RE_FECHA = re.compile(r"(\d{1,2})/(\d{1,2})")


def parsear_fechas_col_l(
    texto: str,
    anio: int | None = None,
    fecha_emision: date | None = None,
) -> list[date]:
    """
    "Ch 08/05 - 10/05 - 11/05 - 12/05" -> [date(2026,5,8), date(2026,5,10), ...]
    Retorna [] si el texto no contiene fechas (ej. "transferencia").

    Si se provee fecha_emision, cualquier fecha parseada que quede antes de la
    emisión se desplaza al año siguiente (cubre pagos con vencimientos en
    enero/febrero cuando se emiten en noviembre/diciembre).
    """
    ref = fecha_emision or date.today()
    if anio is None:
        anio = ref.year

    fechas = []
    for m in _RE_FECHA.finditer(texto):
        dia, mes = int(m.group(1)), int(m.group(2))
        try:
            d = date(anio, mes, dia)
        except ValueError:
            continue
        # Si la fecha cae antes de la emisión, probablemente es del año siguiente
        if fecha_emision is not None and d < fecha_emision:
            try:
                d = date(anio + 1, mes, dia)
            except ValueError:
                pass
        fechas.append(d)
    return fechas


def es_cheque(texto: str) -> bool:
    t = (texto or "").strip().lower()
    return bool(re.search(r"\bch\s*\d", t))


def es_transferencia(texto: str) -> bool:
    t = (texto or "").strip().lower()
    return t in {"transferencia", "transferencia interbancaria"}
