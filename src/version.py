"""Identidad del build.

`VERSION` se sube a mano cuando corresponde. `BUILD_SHA` y `BUILD_DATE` los
reescribe el CI antes de compilar (ver `.github/workflows/release.yml`), así que
en el repo quedan vacíos: un build local es "dev" y no chequea actualizaciones.
"""

VERSION = "1.1.0"
BUILD_SHA = ""      # commit del que salió este .exe
BUILD_DATE = ""     # ISO-8601 UTC de la compilación


def es_build_oficial() -> bool:
    """True si lo compiló el CI. Un build local no busca actualizaciones."""
    return bool(BUILD_SHA)


def etiqueta() -> str:
    """Texto corto para el título de la ventana."""
    if not es_build_oficial():
        return f"{VERSION} · dev"
    return f"{VERSION} · {BUILD_SHA[:7]}"


def etiqueta_larga() -> str:
    """Texto completo para «Acerca de» y Configuración."""
    if not es_build_oficial():
        return f"Versión {VERSION} (build local, sin actualizaciones automáticas)"
    fecha = BUILD_DATE[:10] if BUILD_DATE else "?"
    return f"Versión {VERSION} · commit {BUILD_SHA[:7]} · compilado {fecha}"
