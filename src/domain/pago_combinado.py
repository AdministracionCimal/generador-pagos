"""Armado de un pago con varios medios: endosos + cheques propios + transferencia.

Traduce los tramos de «Forma de pago» y la cartera de cheques en los objetos que
consume el mapper. Vive en el dominio (y no en `main_window`) para poder testear
la aritmética contra una OP real de Finnegans.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from . import cartera as cartera_mod
from .bancos import resolver_codigo
from .forma_pago import (
    CHEQUE,
    ENDOSO,
    TRANSFERENCIA,
    RepartoError,
    Tramo,
    repartir,
)
from .fraccionador import fraccionar_importe
from .models import ChequeEmitido, ChequeEndosado, ProveedorTanda


class PagoCombinado:
    """Resultado del armado: qué paga cada medio."""

    def __init__(
        self,
        cheques: list[ChequeEmitido],
        endosos: list[ChequeEndosado],
        importe_transferencia: Decimal | None,
        proximo_numero_cheque: int,
    ) -> None:
        self.cheques = cheques
        self.endosos = endosos
        self.importe_transferencia = importe_transferencia
        self.proximo_numero_cheque = proximo_numero_cheque

    @property
    def total(self) -> Decimal:
        return (
            sum((c.importe for c in self.cheques), Decimal("0"))
            + sum((e.importe for e in self.endosos), Decimal("0"))
            + (self.importe_transferencia or Decimal("0"))
        )


def armar(
    proveedor: ProveedorTanda,
    tramos: list[Tramo],
    retencion_total: Decimal,
    cheques_cartera: list,
    mapa_bancos: dict[str, str],
    numero_desde: int,
    fecha_emision: date,
) -> PagoCombinado:
    """Reparte el importe del proveedor entre los tramos indicados.

    Levanta `RepartoError` con un mensaje para el usuario cuando el pago no se
    puede armar solo (endoso que no cierra, cheque que no está en cartera, banco
    que no se puede resolver): esos casos van a carga manual.
    """
    numeros = [n for t in tramos if t.tipo == ENDOSO for n in t.numeros_cheque]
    importes_endoso = cartera_mod.importes_por_numero(cheques_cartera, numeros)

    partes = repartir(
        tramos,
        importe_a_pagar=proveedor.importe_total,
        retencion_total=retencion_total,
        importes_endoso=importes_endoso,
    )

    cheques: list[ChequeEmitido] = []
    endosos: list[ChequeEndosado] = []
    importe_transferencia: Decimal | None = None
    siguiente = numero_desde

    for parte in partes:
        if parte.tramo.tipo == ENDOSO:
            for numero in parte.tramo.numeros_cheque:
                endosos.append(_a_endosado(numero, cheques_cartera, mapa_bancos))
        elif parte.tramo.tipo == CHEQUE:
            nuevos, siguiente = fraccionar_importe(
                parte.importe,
                parte.tramo.fechas_texto,
                numero_desde=siguiente,
                fecha_emision=fecha_emision,
                fecha_fallback=_fecha_vto_de_respaldo(proveedor),
            )
            cheques.extend(nuevos)
        elif parte.tramo.tipo == TRANSFERENCIA:
            importe_transferencia = parte.importe

    return PagoCombinado(cheques, endosos, importe_transferencia, siguiente)


def _a_endosado(numero: str, cheques_cartera: list, mapa_bancos: dict[str, str]) -> ChequeEndosado:
    cheque = cartera_mod.buscar(cheques_cartera, numero)
    if cheque is None:                        # repartir() ya lo habría rechazado
        raise RepartoError(f"no se encontró en cartera el cheque {numero}")

    banco_codigo = resolver_codigo(mapa_bancos, cheque.banco)
    if not banco_codigo:
        raise RepartoError(
            f"no se pudo determinar el código del banco «{cheque.banco}» del cheque "
            f"{cheque.numero}"
        )

    return ChequeEndosado(
        documento_fisico_id=cheque.documento_fisico_id,
        numero=cheque.numero,
        importe=cheque.importe,
        fecha_emision=cheque.fecha_emision,
        fecha_vencimiento=cheque.fecha_vencimiento,
        banco_codigo=banco_codigo,
        librador=cheque.librador,
        banco_nombre=cheque.banco,
    )


def _fecha_vto_de_respaldo(proveedor: ProveedorTanda) -> date | None:
    """Primera «Fecha vto» del Excel, para el caso de un tramo de cheque sin fechas."""
    return next((i.fecha_vto for i in proveedor.items if i.fecha_vto is not None), None)
