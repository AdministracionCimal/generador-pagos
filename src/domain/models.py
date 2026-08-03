from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import Enum, auto


class Modalidad(Enum):
    CHEQUE_PROPIO = auto()
    TRANSFERENCIA = auto()
    MANUAL = auto()


@dataclass
class ItemFactura:
    documento: str          # "FC - 21562" / "MOVFONDOS - 10845"
    comprobante: str        # "A-0001-00000123" / "F-0000-00010823"
    descripcion: str        # col H
    importe: Decimal
    fecha_vto: date | None
    modalidad_pago: str     # col L raw, ej "Ch 08/05 - 10/05"


@dataclass
class ProveedorTanda:
    cuit: str
    nombre: str
    items: list[ItemFactura] = field(default_factory=list)
    modalidad: Modalidad = Modalidad.MANUAL
    motivo_manual: str = ""
    avisos: list[str] = field(default_factory=list)   # advertencias no-fatales (ej. typos)

    @property
    def importe_total(self) -> Decimal:
        return sum(i.importe for i in self.items)


@dataclass
class ChequeEmitido:
    numero: str
    importe: Decimal
    fecha_emision: date
    fecha_vencimiento: date
    # Token del Excel que no era una fecha válida (ej. "31/02"). Si está seteado,
    # `fecha_vencimiento` es provisoria: el usuario tiene que corregirla en la
    # pantalla previa y la app se niega a enviar el cheque hasta entonces.
    fecha_origen_invalida: str = ""
    # El usuario confirmó en la pantalla previa que el plazo largo (más de
    # ALERTA_FUTURO_DIAS) es correcto. Sólo levanta esa alerta, no las demás.
    plazo_confirmado: bool = False


@dataclass
class OpPago:
    proveedor: ProveedorTanda
    cheques: list[ChequeEmitido] = field(default_factory=list)
    numero_comprobante_estimado: str = ""
    chequera_codigo: str = ""
    banco_codigo: str = ""
    cuenta_banco_codigo: str = ""
    cuenta_proveedor_codigo: str = "02.01.01.01.0001"
    op_bancaria_cheque_codigo: str = "EMCHPROP"
    op_bancaria_transferencia_codigo: str = "TLote"
    empresa_codigo: str = "EMPRE01"
    cotizacion_dolar: Decimal = field(default_factory=lambda: Decimal("1"))
    retenciones: list[dict] = field(default_factory=list)
    fecha: date = field(default_factory=date.today)
