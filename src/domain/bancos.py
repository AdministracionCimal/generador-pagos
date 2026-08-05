"""Nombre de banco → código, para el tramo de endoso del POST.

El reporte de cartera devuelve el **nombre** del banco del librador
(`BANCO PATAGONIA S.A.`) pero la OP necesita su **código** (`00034`), que sale de
`/banco/list`. Por suerte los nombres coinciden entre los dos lados (con las
empresas no pasaba), así que el cruce es directo; igual se normaliza antes de
comparar para no depender de tildes, puntos ni espacios de más.
"""
from __future__ import annotations

import re
import unicodedata


def normalizar(nombre) -> str:
    """`«Banco  Patagonia S.A.»` → `«BANCOPATAGONIASA»`.

    Se descarta todo lo que no sea alfanumérico: así `S.A.`, `S. A.` y `SA`
    colapsan al mismo texto y el cruce no depende de cómo se escribió el nombre.
    """
    texto = unicodedata.normalize("NFD", str(nombre or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9]", "", texto).upper()


def mapa_por_nombre(bancos: list[dict]) -> dict[str, str]:
    """`{nombre normalizado: código}` a partir de `/banco/list`."""
    mapa: dict[str, str] = {}
    for banco in bancos:
        codigo = str(banco.get("codigo") or banco.get("Codigo") or "").strip()
        nombre = normalizar(banco.get("nombre") or banco.get("Nombre") or "")
        if codigo and nombre:
            mapa.setdefault(nombre, codigo)
    return mapa


def resolver_codigo(mapa: dict[str, str], nombre: str) -> str | None:
    """Código del banco, o None si no se puede resolver sin ambigüedad.

    Primero por nombre exacto (normalizado); si no está, por coincidencia parcial
    **sólo si es única**: dos bancos que empiecen igual no se adivinan.
    """
    buscado = normalizar(nombre)
    if not buscado:
        return None
    if buscado in mapa:
        return mapa[buscado]

    candidatos = {
        codigo for registrado, codigo in mapa.items()
        if registrado.startswith(buscado) or buscado.startswith(registrado)
    }
    if len(candidatos) == 1:
        return candidatos.pop()
    return None
