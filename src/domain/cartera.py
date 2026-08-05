"""Cheques de terceros en cartera, para endosar a un proveedor.

Vienen del reporte `ApiSituacionCheques` de Finnegans (`TipoCheque=1`,
`Estado="En Cartera"`).

Cuidado que salió de mirar los datos reales: **la respuesta mezcla empresas del
grupo**, así que hay que consultarla filtrando por empresa y además verificar que
lo que volvió sea de una sola.

Un cheque endosado **puede tener vencimiento anterior a la fecha del pago** y eso
es normal: a diferencia de un cheque propio, acá no se emite nada, se entrega un
valor que ya existe. `vencidos()` es sólo informativo — **no** bloquea el envío ni
genera alerta.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation


class CarteraError(Exception):
    pass


def _fecha(crudo) -> date | None:
    """El reporte devuelve `dd-mm-yyyy`."""
    if not crudo:
        return None
    try:
        return datetime.strptime(str(crudo).strip(), "%d-%m-%Y").date()
    except ValueError:
        return None


def _importe(crudo) -> Decimal:
    try:
        return Decimal(str(crudo or 0))
    except InvalidOperation:
        return Decimal("0")


def _sin_ceros(numero: str) -> str:
    """`«00017»` → `«17»`, para comparar con lo que escribe el usuario."""
    limpio = str(numero or "").strip().lstrip("0")
    return limpio or "0"


@dataclass(frozen=True)
class ChequeCartera:
    documento_fisico_id: int
    numero: str
    numero_electronico: str
    banco: str
    librador: str
    cuit_librador: str
    fecha_emision: date | None
    fecha_vencimiento: date | None
    importe: Decimal
    empresa: str

    def coincide_con(self, escrito: str) -> bool:
        """True si el número escrito en el Excel refiere a este cheque.

        Se comparan los dos números que trae el reporte (el del cheque y el
        electrónico, que difieren en algunos casos) ignorando ceros a la
        izquierda: en cartera figuran como «00017» y el usuario puede escribir 17.
        """
        objetivo = _sin_ceros(escrito)
        return objetivo in {_sin_ceros(self.numero), _sin_ceros(self.numero_electronico)}


def leer_cartera(filas: list[dict]) -> list[ChequeCartera]:
    """Traduce las filas del reporte. Descarta las que no tienen identificador."""
    cheques: list[ChequeCartera] = []
    for fila in filas:
        doc_id = fila.get("DOCUMENTOFISICOID")
        if doc_id in (None, ""):
            continue
        cheques.append(ChequeCartera(
            documento_fisico_id=int(doc_id),
            numero=str(fila.get("NUMERO") or "").strip(),
            numero_electronico=str(fila.get("NROCHEQUEELECTRONICO") or "").strip(),
            banco=str(fila.get("BANCO") or "").strip(),
            librador=str(fila.get("TERCERO") or "").strip(),
            cuit_librador=str(fila.get("CUITLIBRADOR") or "").strip(),
            fecha_emision=_fecha(fila.get("FECHAEMISION")),
            fecha_vencimiento=_fecha(fila.get("FECHAVENCIMIENTO")),
            importe=_importe(fila.get("IMPORTEMONTRANSACCION")),
            empresa=str(fila.get("EMPRESA") or "").strip(),
        ))
    return cheques


def buscar(cheques: list[ChequeCartera], escrito: str) -> ChequeCartera | None:
    return next((c for c in cheques if c.coincide_con(escrito)), None)


def importes_por_numero(cheques: list[ChequeCartera], escritos: list[str]) -> dict[str, Decimal]:
    """`{número tal como lo escribió el usuario: importe}` para `repartir()`.

    Los que no están en cartera quedan afuera: `repartir()` los reporta.
    """
    encontrados = {}
    for escrito in escritos:
        cheque = buscar(cheques, escrito)
        if cheque is not None:
            encontrados[escrito] = cheque.importe
    return encontrados


def empresas(cheques: list[ChequeCartera]) -> set[str]:
    return {c.empresa for c in cheques if c.empresa}


def validar_una_empresa(cheques: list[ChequeCartera]) -> None:
    """El filtro por empresa se hace en el servidor; esto verifica que se aplicó.

    Si el reporte devuelve cheques de varias empresas, el parámetro no tomó
    (pasa, por ejemplo, si se manda el ID interno `EMPRESA_EMPRE01`) y endosar
    desde esa lista podría usar un cheque de otra sociedad del grupo.
    """
    presentes = empresas(cheques)
    if len(presentes) > 1:
        raise CarteraError(
            "el reporte devolvió cheques de más de una empresa "
            f"({', '.join(sorted(presentes))}): no se aplicó el filtro por empresa"
        )


def vencidos(cheques: list[ChequeCartera], hoy: date | None = None) -> list[ChequeCartera]:
    """Cheques con vencimiento pasado. **Informativo**: endosar uno vencido es
    válido, así que esto no bloquea ni alerta, sólo permite mostrarlo."""
    hoy = hoy or date.today()
    return [
        c for c in cheques
        if c.fecha_vencimiento is not None and c.fecha_vencimiento < hoy
    ]
