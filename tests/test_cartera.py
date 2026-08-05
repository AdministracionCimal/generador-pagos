"""Lectura de los cheques de terceros en cartera."""
from datetime import date
from decimal import Decimal

import pytest

from src.api.endpoints import Endpoints
from src.domain.cartera import (
    CarteraError,
    buscar,
    empresas,
    importes_por_numero,
    leer_cartera,
    validar_una_empresa,
    vencidos,
)
from src.domain.empresa import codigo_limpio

# Fila real del reporte ApiSituacionCheques (datos cambiados).
FILA = {
    "TRANSACCIONID": 105885,
    "CUENTA": "Valores a Depositar",
    "BANCO": "BANCO SANTANDER RIO S.A.",
    "NUMERO": "00017",
    "NROCHEQUEELECTRONICO": "00017735",
    "TERCERO": "PROVEEDOR DE PRUEBA SA",
    "IDTRIBUTARIA": "30-11111111-7",
    "DOCUMENTO": "COBRANZA - 2709",
    "FECHAEMISION": "02-01-2026",
    "FECHAVENCIMIENTO": "03-03-2026",
    "IMPORTEMONTRANSACCION": 1429343.4,
    "MONEDA": "Pesos",
    "EMPRESA": "CIMALCO NEUQUEN S.A.",
    "CONCILIADO": "No",
    "DOCUMENTOFISICOID": 16655,
    "ESTADO": "En Cartera",
    "CUITLIBRADOR": "30-11111111-7",
}


def _fila(**cambios) -> dict:
    return {**FILA, **cambios}


class TestLeerCartera:
    def test_traduce_los_campos(self):
        cheque = leer_cartera([FILA])[0]
        assert cheque.documento_fisico_id == 16655
        assert cheque.numero == "00017"
        assert cheque.numero_electronico == "00017735"
        assert cheque.banco == "BANCO SANTANDER RIO S.A."
        assert cheque.librador == "PROVEEDOR DE PRUEBA SA"
        assert cheque.importe == Decimal("1429343.4")
        assert cheque.empresa == "CIMALCO NEUQUEN S.A."

    def test_parsea_las_fechas_en_formato_dd_mm_yyyy(self):
        cheque = leer_cartera([FILA])[0]
        assert cheque.fecha_emision == date(2026, 1, 2)
        assert cheque.fecha_vencimiento == date(2026, 3, 3)

    def test_fecha_invalida_queda_en_none(self):
        cheque = leer_cartera([_fila(FECHAVENCIMIENTO="")])[0]
        assert cheque.fecha_vencimiento is None

    def test_descarta_filas_sin_identificador(self):
        assert leer_cartera([_fila(DOCUMENTOFISICOID=None)]) == []


class TestBuscarPorNumero:
    def test_por_el_numero_tal_cual(self):
        cheques = leer_cartera([FILA])
        assert buscar(cheques, "00017") is not None

    def test_ignorando_ceros_a_la_izquierda(self):
        """En cartera figura «00017» y el usuario puede escribir 17."""
        cheques = leer_cartera([FILA])
        assert buscar(cheques, "17") is not None

    def test_por_el_numero_electronico(self):
        cheques = leer_cartera([FILA])
        assert buscar(cheques, "00017735") is not None
        assert buscar(cheques, "17735") is not None

    def test_numero_que_no_esta(self):
        assert buscar(leer_cartera([FILA]), "99999") is None

    def test_importes_por_numero_solo_devuelve_los_encontrados(self):
        cheques = leer_cartera([FILA])
        importes = importes_por_numero(cheques, ["17", "99999"])
        assert importes == {"17": Decimal("1429343.4")}


class TestFiltroPorEmpresa:
    def test_una_sola_empresa_pasa(self):
        validar_una_empresa(leer_cartera([FILA, _fila(DOCUMENTOFISICOID=2)]))

    def test_varias_empresas_es_error(self):
        """Pasa si el filtro del reporte no tomó: podríamos endosar un cheque de
        otra sociedad del grupo."""
        cheques = leer_cartera([FILA, _fila(DOCUMENTOFISICOID=2, EMPRESA="PER SAS")])
        with pytest.raises(CarteraError, match="más de una empresa"):
            validar_una_empresa(cheques)

    def test_empresas_presentes(self):
        cheques = leer_cartera([FILA, _fila(DOCUMENTOFISICOID=2, EMPRESA="PER SAS")])
        assert empresas(cheques) == {"CIMALCO NEUQUEN S.A.", "PER SAS"}


class TestVencidos:
    """Informativo únicamente: endosar un cheque con vencimiento anterior a la
    fecha del pago es válido (no se emite nada, se entrega un valor existente),
    así que esto NO bloquea ni alerta."""

    HOY = date(2026, 8, 4)

    def test_detecta_el_vencido(self):
        viejo = _fila(DOCUMENTOFISICOID=2, FECHAVENCIMIENTO="18-01-2025")
        cheques = leer_cartera([_fila(FECHAVENCIMIENTO="30-08-2026"), viejo])
        assert [c.documento_fisico_id for c in vencidos(cheques, self.HOY)] == [2]

    def test_el_que_vence_hoy_no_esta_vencido(self):
        cheques = leer_cartera([_fila(FECHAVENCIMIENTO="04-08-2026")])
        assert vencidos(cheques, self.HOY) == []


class TestCodigoDeEmpresa:
    def test_saca_el_prefijo_interno(self):
        assert codigo_limpio("EMPRESA_EMPRE01") == "EMPRE01"

    def test_es_idempotente(self):
        assert codigo_limpio("EMPRE01") == "EMPRE01"

    def test_tolera_espacios_y_no_strings(self):
        assert codigo_limpio("  EMPRESA_EMPRE01 ") == "EMPRE01"
        assert codigo_limpio(None) is None


class TestUrlDelReporte:
    def test_arma_los_parametros_obligatorios(self):
        url = Endpoints("https://api.finneg.com/api").situacion_cheques(
            "TOK", "2026-08-04", empresa="EMPRE01"
        )
        assert "/reports/ApiSituacionCheques" in url
        assert "PARAMWEBREPORT_TipoCheque=1" in url
        assert "PARAMWEBREPORT_Estado=En%20Cartera" in url   # por nombre, no código
        assert "PARAMWEBREPORT_FechaHasta=2026-08-04" in url
        assert "PARAMWEBREPORT_Empresa=EMPRE01" in url

    def test_sin_empresa_no_manda_el_parametro(self):
        url = Endpoints("https://api.finneg.com/api").situacion_cheques("TOK", "2026-08-04")
        assert "PARAMWEBREPORT_Empresa" not in url
