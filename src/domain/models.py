from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import Enum, auto


class Modalidad(Enum):
    CHEQUE_PROPIO = auto()
    TRANSFERENCIA = auto()
    COMBINADO = auto()      # varios medios en la misma «Forma de pago», por porcentaje
    MIXTO = auto()          # cada factura con su medio (una por transferencia, otra en cheques)
    MANUAL = auto()


@dataclass
class ItemFactura:
    documento: str          # "FC - 21562" / "MOVFONDOS - 10845"
    comprobante: str        # "A-0001-00000123" / "F-0000-00010823"
    descripcion: str        # col H
    importe: Decimal
    fecha_vto: date | None
    modalidad_pago: str     # col L raw, ej "Ch 08/05 - 10/05"
    # Con qué se aplica el pago en el POST. Lo completa _construir_ops con la
    # IdentificacionExterna que devolvió composicionSaldoProveedor: mandar el
    # documento interno hace que la OP se cree pero no quede aplicada. Vacío =
    # no se pudo consultar el saldo, y se cae a `documento`.
    aplicacion_origen: str = ""


@dataclass
class ProveedorTanda:
    cuit: str
    nombre: str
    items: list[ItemFactura] = field(default_factory=list)
    modalidad: Modalidad = Modalidad.MANUAL
    motivo_manual: str = ""
    avisos: list[str] = field(default_factory=list)   # advertencias no-fatales (ej. typos)
    # Sólo en modalidad COMBINADO: los tramos de «Forma de pago» ya parseados
    # (todos los ítems pagables comparten el mismo texto).
    tramos: list = field(default_factory=list)

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
class ChequeEndosado:
    """Cheque de tercero en cartera que se entrega al proveedor.

    Va aparte de `ChequeEmitido` a propósito: acá no se emite nada, así que el
    vencimiento puede ser anterior a la fecha del pago y **no** corresponde
    aplicarle las alertas de fecha de los cheques propios.
    """
    documento_fisico_id: int
    numero: str
    importe: Decimal
    fecha_emision: date | None
    fecha_vencimiento: date | None
    banco_codigo: str
    librador: str = ""
    banco_nombre: str = ""


@dataclass
class OpPago:
    proveedor: ProveedorTanda
    cheques: list[ChequeEmitido] = field(default_factory=list)
    endosos: list[ChequeEndosado] = field(default_factory=list)
    # Parte del pago que sale por transferencia. None = no hay tramo de
    # transferencia (para la modalidad TRANSFERENCIA pura se calcula en el mapper).
    importe_transferencia: Decimal | None = None
    numero_comprobante_estimado: str = ""
    chequera_codigo: str = ""
    banco_codigo: str = ""
    cuenta_banco_codigo: str = ""
    # Sólo en pagos combinados: los cheques propios y la transferencia salen de
    # cuentas distintas. Si queda vacía se usa `cuenta_banco_codigo` (que es lo
    # que hace la modalidad TRANSFERENCIA pura).
    cuenta_banco_transferencia_codigo: str = ""
    cuenta_proveedor_codigo: str = "02.01.01.01.0001"
    op_bancaria_cheque_codigo: str = "EMCHPROP"
    op_bancaria_transferencia_codigo: str = "TLote"
    op_bancaria_endoso_codigo: str = "CHENDOSADOS"
    cuenta_valores_codigo: str = "01.01.01.03.0001"   # Valores a Depositar
    empresa_codigo: str = "EMPRE01"
    cotizacion_dolar: Decimal = field(default_factory=lambda: Decimal("1"))
    retenciones: list[dict] = field(default_factory=list)
    fecha: date = field(default_factory=date.today)
