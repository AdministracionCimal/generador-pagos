"""Armado de un pago con varios medios: endosos + cheques propios + transferencia.

Traduce los tramos de «Forma de pago» y la cartera de cheques en los objetos que
consume el mapper. Vive en el dominio (y no en `main_window`) para poder testear
la aritmética contra una OP real de Finnegans.
"""
from __future__ import annotations

from dataclasses import replace as _dc_replace
from datetime import date
from decimal import ROUND_DOWN, Decimal

from . import cartera as cartera_mod
from .bancos import resolver_codigo
from .forma_pago import (
    CHEQUE,
    ENDOSO,
    TRANSFERENCIA,
    RepartoError,
    Tramo,
    parsear_tramos,
    pesos as _pesos,
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


def armar_por_item(
    proveedor: ProveedorTanda,
    retencion_total: Decimal,
    cheques_cartera: list,
    mapa_bancos: dict[str, str],
    numero_desde: int,
    fecha_emision: date,
) -> PagoCombinado:
    """Cada factura se paga con el medio que indica su propia «Forma de pago».

    Es el caso de un proveedor con varias facturas donde algunas van por
    transferencia y otras en cheques (con las fechas de cada una). No hay
    porcentajes: el importe de cada tramo es la suma de las facturas que lo eligen.

    **Las deducciones —retenciones y créditos— salen de la transferencia** y, si no
    alcanza o no hay, de los cheques. Nunca del endoso, cuyo importe es el nominal
    del cheque de cartera. Criterio del usuario: pagar menos ahora, más a plazo.
    """
    pagables = [i for i in proveedor.items if i.importe > 0]
    creditos = sum((i.importe for i in proveedor.items if i.importe < 0), Decimal("0"))

    por_medio: dict[str, list] = {CHEQUE: [], TRANSFERENCIA: [], ENDOSO: []}
    for item in pagables:
        tramos = parsear_tramos(item.modalidad_pago)
        if len(tramos) != 1 or tramos[0].porcentaje is not None:
            raise RepartoError(
                f"«{item.modalidad_pago}» en {item.documento}: para mezclar medios "
                f"entre facturas, cada fila tiene que indicar un solo medio sin porcentaje"
            )
        por_medio[tramos[0].tipo].append((item, tramos[0]))

    # Los créditos (PAGO, NC, MOVFONDOS positivo) vienen en negativo: restarlos
    # los suma a lo que hay que deducir.
    deducciones = retencion_total - creditos

    endosos: list[ChequeEndosado] = []
    for item, tramo in por_medio[ENDOSO]:
        nominal = Decimal("0")
        for numero in tramo.numeros_cheque:
            endosado = _a_endosado(numero, cheques_cartera, mapa_bancos)
            endosos.append(endosado)
            nominal += endosado.importe
        if nominal != item.importe:
            diferencia = nominal - item.importe
            raise RepartoError(
                f"{item.documento}: los cheques a endosar suman {_pesos(nominal)} y la "
                f"factura es de {_pesos(item.importe)} "
                f"({'sobran' if diferencia > 0 else 'faltan'} {_pesos(abs(diferencia))})"
            )
    _validar_endosos_unicos(endosos)

    bruto_transf = sum((i.importe for i, _ in por_medio[TRANSFERENCIA]), Decimal("0"))
    items_cheque = [i for i, _ in por_medio[CHEQUE]]
    bruto_cheques = sum((i.importe for i in items_cheque), Decimal("0"))

    # La transferencia absorbe primero; el remanente va a los cheques.
    a_transferencia = min(deducciones, bruto_transf)
    resto_deducciones = deducciones - a_transferencia
    if resto_deducciones > bruto_cheques:
        raise RepartoError(
            f"las deducciones ({_pesos(deducciones)}) superan lo que se paga "
            f"({_pesos(bruto_transf + bruto_cheques)})"
        )

    importe_transferencia = (
        bruto_transf - a_transferencia if por_medio[TRANSFERENCIA] else None
    )

    cheques: list[ChequeEmitido] = []
    siguiente = numero_desde
    for item in _restar_proporcional(items_cheque, resto_deducciones):
        nuevos, siguiente = fraccionar_importe(
            item.importe,
            item.modalidad_pago,
            numero_desde=siguiente,
            fecha_emision=fecha_emision,
            fecha_fallback=item.fecha_vto,
        )
        cheques.extend(nuevos)

    return PagoCombinado(cheques, endosos, importe_transferencia, siguiente)


def _restar_proporcional(items: list, monto: Decimal) -> list:
    """Reparte `monto` entre los ítems en proporción a su importe.

    Sólo se usa cuando la transferencia no alcanzó a absorber las deducciones. El
    último ítem se queda con los centavos del redondeo.
    """
    if monto <= 0 or not items:
        return items
    total = sum((i.importe for i in items), Decimal("0"))
    restado = Decimal("0")
    ajustados = []
    for n, item in enumerate(items, 1):
        if n == len(items):
            quita = monto - restado
        else:
            quita = (monto * item.importe / total).quantize(
                Decimal("0.01"), rounding=ROUND_DOWN
            )
            restado += quita
        ajustados.append(_dc_replace(item, importe=item.importe - quita))
    return ajustados


def _validar_endosos_unicos(endosos: list[ChequeEndosado]) -> None:
    """El mismo cheque de cartera no puede endosarse dos veces en la misma OP."""
    vistos: set[int] = set()
    for e in endosos:
        if e.documento_fisico_id in vistos:
            raise RepartoError(
                f"el cheque {e.numero} está indicado para endosar más de una vez"
            )
        vistos.add(e.documento_fisico_id)


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
