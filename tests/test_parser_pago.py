from datetime import date

import pytest

from src.domain.parser_pago import es_cheque, es_transferencia, parsear_fechas_col_l


class TestParsearFechas:
    def test_multiples_fechas(self):
        resultado = parsear_fechas_col_l("Ch 08/05 - 10/05 - 11/05 - 12/05", anio=2026)
        assert resultado == [
            date(2026, 5, 8),
            date(2026, 5, 10),
            date(2026, 5, 11),
            date(2026, 5, 12),
        ]

    def test_una_fecha(self):
        resultado = parsear_fechas_col_l("Ch 15/05", anio=2026)
        assert resultado == [date(2026, 5, 15)]

    def test_transferencia_sin_fechas(self):
        assert parsear_fechas_col_l("transferencia", anio=2026) == []

    def test_vacio(self):
        assert parsear_fechas_col_l("", anio=2026) == []

    def test_rango_bimestral(self):
        resultado = parsear_fechas_col_l("Ch 08/06 - 09/06 - 18/06 - 19/06 - 05/07 - 06/07", anio=2026)
        assert len(resultado) == 6
        assert resultado[0] == date(2026, 6, 8)
        assert resultado[-1] == date(2026, 7, 6)


class TestEsCheque:
    def test_formato_tipico(self):
        assert es_cheque("Ch 08/05 - 10/05 - 11/05 - 12/05")

    def test_ch_solo(self):
        assert es_cheque("Ch 15/05")

    def test_ch_sin_espacio(self):
        assert es_cheque("ch08/05")

    def test_ch_sin_espacio_mayuscula(self):
        assert es_cheque("Ch08/05 - 10/05")

    def test_no_es_cheque_transferencia(self):
        assert not es_cheque("transferencia")

    def test_no_es_cheque_vacio(self):
        assert not es_cheque("")


class TestEsTransferencia:
    def test_transferencia(self):
        assert es_transferencia("transferencia")

    def test_transferencia_interbancaria(self):
        assert es_transferencia("Transferencia Interbancaria")

    def test_no_es_transf_cheque(self):
        assert not es_transferencia("Ch 08/05")

    def test_no_es_transf_tarjeta(self):
        assert not es_transferencia("Tarjeta de Crédito")
