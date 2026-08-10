"""Gramática de «Forma de pago» con varios medios en la misma celda.

Un proveedor puede pagarse combinando tramos separados por `+`:

    Ch 10/09 + transferencia 30%
    Endoso 11139918 + Ch 10/09
    Endoso 11139918 - 03744630 + transferencia

Reglas del reparto (sobre el **importe a pagar** = bruto − créditos):

1. El **endoso** va por el nominal exacto del cheque en cartera: no se fracciona
   ni se le descuenta nada.
2. Los tramos con `%` toman ese porcentaje del importe a pagar.
3. El tramo **sin** `%` hace de resto: se queda con lo que sobra y con los
   centavos del redondeo.
4. La **retención** se descuenta de la transferencia; si no hay, del cheque
   propio. Nunca del endoso. Criterio del usuario: pagar menos ahora (efectivo)
   y más a plazo (cheque).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from .parser_pago import es_cheque, es_transferencia, parsear_slots_fecha

CHEQUE        = "CHEQUE"
TRANSFERENCIA = "TRANSFERENCIA"
ENDOSO        = "ENDOSO"

_RE_PORCENTAJE = re.compile(r"(\d+(?:[.,]\d+)?)\s*%")
_RE_ENDOSO     = re.compile(r"\b(?:endosos?|end)\b", re.I)
# 2+ dígitos: los números de cartera vienen con ceros a la izquierda («00017»),
# pero el usuario puede escribirlos sin relleno («17»). Un dígito solo se ignora
# para no confundir un «Endoso 2 cheques …» con un número.
_RE_NRO_CHEQUE = re.compile(r"\d{2,}")
_CIEN = Decimal("100")


@dataclass
class Tramo:
    tipo: str                                    # CHEQUE | TRANSFERENCIA | ENDOSO
    texto: str                                   # tal como venía en el Excel
    porcentaje: Decimal | None = None
    fechas_texto: str = ""                       # para CHEQUE: el texto sin el %
    numeros_cheque: list[str] = field(default_factory=list)   # para ENDOSO

    @property
    def es_endoso(self) -> bool:
        return self.tipo == ENDOSO


def _a_decimal_porcentaje(crudo: str) -> Decimal:
    return Decimal(crudo.replace(",", "."))


def parsear_tramos(texto: str) -> list[Tramo]:
    """Divide «Forma de pago» en tramos. Lista vacía si no se reconoce ninguno."""
    tramos: list[Tramo] = []
    for parte in str(texto or "").split("+"):
        crudo = parte.strip()
        if not crudo:
            continue
        tramo = _parsear_tramo(crudo)
        if tramo is not None:
            tramos.append(tramo)
    return tramos


def _parsear_tramo(crudo: str) -> Tramo | None:
    match_pct = _RE_PORCENTAJE.search(crudo)
    porcentaje = _a_decimal_porcentaje(match_pct.group(1)) if match_pct else None
    # El % se saca antes de mirar fechas para que «70%» no se confunda con nada.
    sin_pct = _RE_PORCENTAJE.sub(" ", crudo).strip()

    if _RE_ENDOSO.search(sin_pct):
        numeros = _RE_NRO_CHEQUE.findall(sin_pct)
        if not numeros:
            return None
        return Tramo(tipo=ENDOSO, texto=crudo, numeros_cheque=numeros)

    if es_cheque(sin_pct):
        return Tramo(tipo=CHEQUE, texto=crudo, porcentaje=porcentaje, fechas_texto=sin_pct)

    if es_transferencia(sin_pct):
        return Tramo(tipo=TRANSFERENCIA, texto=crudo, porcentaje=porcentaje)

    return None


def motivo_invalido(tramos: list[Tramo]) -> str | None:
    """Por qué la combinación no se puede procesar, o None si está bien."""
    if not tramos:
        return "no se reconoció ninguna forma de pago"

    tipos = [t.tipo for t in tramos]
    for tipo in (CHEQUE, TRANSFERENCIA, ENDOSO):
        if tipos.count(tipo) > 1:
            return f"hay {tipos.count(tipo)} tramos de {tipo.lower()}: escribí uno solo"

    ajustables = [t for t in tramos if not t.es_endoso]
    if not ajustables:
        # Sólo endosos: los cheques tienen que cubrir exactamente el importe.
        return None

    sin_pct = [t for t in ajustables if t.porcentaje is None]
    if len(sin_pct) > 1:
        return "hay más de un tramo sin porcentaje: no se sabe cómo repartir el importe"

    if not sin_pct:
        total = sum((t.porcentaje for t in ajustables), Decimal("0"))
        if total != _CIEN:
            return f"los porcentajes suman {total:g}% en lugar de 100%"

    for tramo in ajustables:
        if tramo.porcentaje is not None and not (Decimal("0") < tramo.porcentaje <= _CIEN):
            return f"porcentaje inválido: {tramo.porcentaje:g}%"

    return None


def tramo_de(tramos: list[Tramo], tipo: str) -> Tramo | None:
    return next((t for t in tramos if t.tipo == tipo), None)


def cheques_previstos(tramos: list[Tramo], fecha_emision: date | None = None) -> int:
    """Cuántos cheques propios va a emitir esta combinación.

    Se usa antes de conocer importes (para la métrica de la tabla y el control de
    límite de la chequera), así que sale de contar fechas, no de repartir.
    """
    tramo = tramo_de(tramos, CHEQUE)
    if tramo is None:
        return 0
    slots = parsear_slots_fecha(tramo.fechas_texto, fecha_emision=fecha_emision)
    return len(slots) or 1


@dataclass
class ParteDelPago:
    tramo: Tramo
    importe: Decimal          # lo que efectivamente paga este tramo
    retencion: Decimal = Decimal("0")   # cuánto absorbió de retenciones


class RepartoError(Exception):
    """El pago no se puede armar solo: el proveedor queda en carga manual."""


def _centavos(valor: Decimal) -> Decimal:
    return valor.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def pesos(valor: Decimal) -> str:
    return f"$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def repartir(
    tramos: list[Tramo],
    importe_a_pagar: Decimal,
    retencion_total: Decimal = Decimal("0"),
    importes_endoso: dict[str, Decimal] | None = None,
) -> list[ParteDelPago]:
    """Cuánto paga cada tramo.

    `importes_endoso` es {número de cheque: importe nominal} de los cheques en
    cartera. La suma de los endosos no puede superar el neto a pagar: si sobra,
    la OP quedaría con saldo a favor involuntario.
    """
    motivo = motivo_invalido(tramos)
    if motivo is not None:
        raise RepartoError(motivo)

    importes_endoso = importes_endoso or {}
    neto = importe_a_pagar - retencion_total

    total_endosos = Decimal("0")
    for tramo in tramos:
        if not tramo.es_endoso:
            continue
        for numero in tramo.numeros_cheque:
            if numero not in importes_endoso:
                raise RepartoError(f"no se encontró en cartera el cheque {numero}")
            total_endosos += importes_endoso[numero]

    # La app sólo arma pagos que cancelan el total exacto. Si el endoso no cierra
    # —por más o por menos— va a carga manual: tocar el importe de la cuenta
    # corriente hace que Finnegans recalcule las retenciones, y eso se resuelve
    # mejor a mano.
    if total_endosos > neto:
        raise RepartoError(
            f"los cheques a endosar suman {pesos(total_endosos)} y el neto a pagar "
            f"es {pesos(neto)}: quedarían {pesos(total_endosos - neto)} a favor "
            f"del proveedor"
        )

    ajustables = [t for t in tramos if not t.es_endoso]
    if not ajustables and total_endosos < neto:
        raise RepartoError(
            f"los cheques a endosar suman {pesos(total_endosos)} y el neto a pagar "
            f"es {pesos(neto)}: faltan {pesos(neto - total_endosos)} y no se indicó "
            f"con qué se pagan"
        )

    # A quién le toca absorber la retención: transferencia > cheque propio.
    absorbe = next((t for t in ajustables if t.tipo == TRANSFERENCIA), None)
    if absorbe is None:
        absorbe = next((t for t in ajustables if t.tipo == CHEQUE), None)
    if absorbe is None and retencion_total > 0:
        raise RepartoError("no hay de dónde descontar la retención: sólo hay endosos")

    partes: list[ParteDelPago] = []
    asignado_bruto = total_endosos

    for tramo in tramos:
        if tramo.es_endoso:
            total = sum(importes_endoso[n] for n in tramo.numeros_cheque)
            partes.append(ParteDelPago(tramo=tramo, importe=total))
            continue
        if tramo.porcentaje is None:
            continue    # el resto se calcula al final
        bruto = _centavos(importe_a_pagar * tramo.porcentaje / _CIEN)
        asignado_bruto += bruto
        partes.append(ParteDelPago(tramo=tramo, importe=bruto))

    resto_tramo = next((t for t in ajustables if t.porcentaje is None), None)
    if resto_tramo is not None:
        partes.append(ParteDelPago(
            tramo=resto_tramo,
            importe=importe_a_pagar - asignado_bruto,
        ))

    # La retención sale de un solo tramo, después de repartir los brutos.
    if retencion_total > 0:
        for parte in partes:
            if parte.tramo is absorbe:
                if parte.importe < retencion_total:
                    raise RepartoError(
                        f"la retención de {retencion_total} no entra en el tramo "
                        f"«{parte.tramo.texto}» de {parte.importe}"
                    )
                parte.importe -= retencion_total
                parte.retencion = retencion_total
                break

    # Devolver en el orden en que venían escritos los tramos.
    orden = {id(t): i for i, t in enumerate(tramos)}
    partes.sort(key=lambda p: orden[id(p.tramo)])
    return partes
