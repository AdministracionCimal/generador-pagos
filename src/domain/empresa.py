"""Código de empresa: un solo lugar donde sacarle el prefijo interno.

`/empresa/list` devuelve el ID interno `EMPRESA_EMPRE01`, pero el resto de
Finnegans espera el código de negocio `EMPRE01`. Mandar el prefijado falla de dos
formas distintas y ninguna es obvia:

- en el POST de la OP: *"El usuario solo tiene permisos de consulta sobre esta
  empresa"* (bug C2);
- en `ApiSituacionCheques`: **HTTP 200 con cero filas**, o sea cartera vacía en
  silencio.
"""
_PREFIJO = "EMPRESA_"


def codigo_limpio(codigo) -> str:
    """`«EMPRESA_EMPRE01»` → `«EMPRE01»`. Idempotente."""
    if not isinstance(codigo, str):
        return codigo
    return codigo.strip().removeprefix(_PREFIJO)
