import unicodedata
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from openpyxl import load_workbook

from src.domain.clasificador import clasificar
from src.domain.models import ItemFactura, ProveedorTanda

HOJA_DM = "DM"

_PREFIJOS_ITEM    = ("fc -", "movfondos -", "nccpra -", "ndcpra -")
_PREFIJOS_CREDITO = ("pago -",)   # saldo a favor: descuenta del total, importe negativo
_PREFIJOS_IGNORAR = ("op -",)     # ya procesadas por Finnegans, se ignoran

def _normalizar(s: str) -> str:
    """Minúsculas y sin tildes para comparar headers."""
    return unicodedata.normalize("NFD", s.lower()).encode("ascii", "ignore").decode()


# Campos que se detectan por coincidencia exacta del header normalizado.
# Evita falsos positivos: "Condicionpago" no debe matchear "pago";
# "Fecha comprobante" no debe matchear "comprobante".
_EXACT = {
    "cuit":        "cuit",
    "documento":   "documento",
    "proveedor":   "proveedor",
    "comprobante": "comprobante",
    "pago":        "pago",
}

# Campos detectados por contener la clave en cualquier parte del header.
_CONTAINS = {
    "importe":  "importe",
    "fecha vto": "fecha_vto",
}


def _detectar_columnas(header_row) -> dict[str, int]:
    """Devuelve {clave: índice_0based} según los headers de la primera fila."""
    cols: dict[str, int] = {}
    partial: dict[str, int] = {}
    for idx, cell in enumerate(header_row):
        norm = _normalizar(str(cell.value or "").strip())
        for keyword, key in _EXACT.items():
            if norm == keyword and key not in cols:
                cols[key] = idx
        for keyword, key in _CONTAINS.items():
            if keyword in norm and key not in partial:
                partial[key] = idx
    for key, idx in partial.items():
        if key not in cols:
            cols[key] = idx
    return cols


def _cel(row, idx: int | None):
    if idx is None or idx >= len(row):
        return None
    return row[idx].value


def _importe(raw) -> Decimal | None:
    if raw is None:
        return None
    try:
        return Decimal(str(raw))
    except InvalidOperation:
        return None


def _fecha(raw) -> date | None:
    if raw is None:
        return None
    if isinstance(raw, date):
        return raw
    return None


def _limpiar_cuit(raw: str) -> str:
    """'30-71018343-7' → '30710183437'"""
    return raw.replace("-", "").replace(".", "").strip()


_AMARILLO = "FFFFFF00"


def _es_fila_amarilla(row) -> bool:
    return any(
        c.fill.fgColor.type == "rgb" and c.fill.fgColor.rgb == _AMARILLO
        for c in row
    )


def leer_dm(path: Path | str, hoja: str = HOJA_DM,
            solo_amarillas: bool = True) -> list[ProveedorTanda]:
    # data_only=True para leer valores calculados; read_only por defecto False (necesario para leer estilos de celda)
    wb = load_workbook(str(path), data_only=True)
    if hoja not in wb.sheetnames:
        hojas_disp = ", ".join(wb.sheetnames)
        wb.close()
        raise ValueError(
            f"No se encontró la hoja «{hoja}» en el archivo.\n"
            f"Hojas disponibles: {hojas_disp}"
        )
    ws = wb[hoja]

    rows = ws.iter_rows()
    header_row = next(rows)
    cols = _detectar_columnas(header_row)

    _COLS_REQUERIDAS = {
        "documento":  "Documento (ej. «FC - 21562»)",
        "proveedor":  "Proveedor",
        "importe":    "Importe",
        "pago":       "Forma de pago",
    }
    faltantes = [label for key, label in _COLS_REQUERIDAS.items() if key not in cols]
    if faltantes:
        wb.close()
        raise ValueError(
            f"Faltan columnas requeridas en la hoja «{hoja}»:\n"
            + "\n".join(f"  • {f}" for f in faltantes)
        )

    proveedores: dict[str, ProveedorTanda] = {}

    for row in rows:
        if not any(c.value for c in row):
            continue
        if solo_amarillas and not _es_fila_amarilla(row):
            continue

        documento = str(_cel(row, cols.get("documento")) or "").strip()
        doc_lower = documento.lower()

        if any(doc_lower.startswith(p) for p in _PREFIJOS_IGNORAR):
            continue
        es_credito = any(doc_lower.startswith(p) for p in _PREFIJOS_CREDITO)
        if not es_credito and not any(doc_lower.startswith(p) for p in _PREFIJOS_ITEM):
            continue

        proveedor_nombre = str(_cel(row, cols.get("proveedor")) or "").strip()
        if not proveedor_nombre:
            continue

        importe_raw = _importe(_cel(row, cols.get("importe")))
        if importe_raw is None:
            continue
        # Créditos (PAGO -) descuentan: siempre negativos.
        # Facturas e items normales: siempre positivos.
        importe = -abs(importe_raw) if es_credito else abs(importe_raw)

        cuit_raw = str(_cel(row, cols.get("cuit")) or "").strip()
        cuit = _limpiar_cuit(cuit_raw) if cuit_raw else ""

        item = ItemFactura(
            documento=documento,
            comprobante=str(_cel(row, cols.get("comprobante")) or "").strip(),
            descripcion="",
            importe=importe,
            fecha_vto=_fecha(_cel(row, cols.get("fecha_vto"))),
            modalidad_pago=str(_cel(row, cols.get("pago")) or "").strip(),
        )

        # A4: agrupar por CUIT cuando está disponible; fallback a nombre
        clave = cuit if cuit else proveedor_nombre
        if clave not in proveedores:
            proveedores[clave] = ProveedorTanda(
                cuit=cuit,
                nombre=proveedor_nombre,
            )
        else:
            existing = proveedores[clave]
            if cuit and not existing.cuit:
                existing.cuit = cuit
        proveedores[clave].items.append(item)

    wb.close()
    return [clasificar(p) for p in proveedores.values()]
