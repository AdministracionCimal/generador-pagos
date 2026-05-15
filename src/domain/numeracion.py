import re


def siguiente_comprobante(numero_actual: str) -> str:
    texto = str(numero_actual or "").strip()
    match = re.search(r"(\d+)(?!.*\d)", texto)
    if not match:
        raise ValueError(f"Número de comprobante inválido: {numero_actual!r}")
    width = len(match.group(1))
    siguiente = f"{int(match.group(1)) + 1:0{width}d}"
    return f"{texto[:match.start(1)]}{siguiente}{texto[match.end(1):]}"


def secuencia_comprobantes(numero_actual: str, cantidad: int) -> list[str]:
    if cantidad <= 0:
        return []
    actual = str(numero_actual or "").strip()
    secuencia: list[str] = []
    for _ in range(cantidad):
        actual = siguiente_comprobante(actual)
        secuencia.append(actual)
    return secuencia
