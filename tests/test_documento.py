from src.domain.documento import es_fc, es_pago, normalizar, tiene_prefijo


class TestNormalizar:
    def test_forma_canonica_no_cambia(self):
        assert normalizar("FC - 21562") == "FC - 21562"

    def test_guion_sin_espacios(self):
        assert normalizar("FC-21562") == "FC - 21562"

    def test_espacios_de_mas_y_minusculas(self):
        assert normalizar("  fc  -   21562  ") == "FC - 21562"

    def test_prefijos_largos(self):
        assert normalizar("movfondos-10845") == "MOVFONDOS - 10845"

    def test_sin_prefijo_queda_igual(self):
        assert normalizar("21562") == "21562"

    def test_none_y_vacio(self):
        assert normalizar(None) == ""
        assert normalizar("   ") == ""


class TestTipoDeDocumento:
    def test_fc_en_todas_sus_formas(self):
        for doc in ("FC - 21562", "FC-21562", "fc - 21562", " Fc -21562 "):
            assert es_fc(doc), doc

    def test_no_confunde_prefijos_parecidos(self):
        # Estos NO son facturas: si se tomaran como FC entrarían en la base
        # imponible de retenciones.
        for doc in ("FCX - 1", "NC - 3021", "ND - 12", "MOVFONDOS - 10845", "21562"):
            assert not es_fc(doc), doc

    def test_pago_en_todas_sus_formas(self):
        for doc in ("PAGO - 14062", "PAGO-14062", "pago -14062"):
            assert es_pago(doc), doc

    def test_pago_no_matchea_otros(self):
        for doc in ("PAGOS - 1", "FC - 14062", "OP - 99999"):
            assert not es_pago(doc), doc

    def test_tiene_prefijo_requiere_numero(self):
        assert not tiene_prefijo("FC", "FC")
        assert tiene_prefijo("FC - 1", "FC")


# ── cruce contra composicionSaldoProveedor ────────────────────────────────────

from src.domain.documento import (
    aplicacion_para,
    claves_de_fila,
    claves_pendientes,
    figura_con_saldo,
    id_externa,
)

# Fila real: factura cargada por Finnegans (IDENTIFICACIONEXTERNA == DOCUMENTO).
FILA_CLASICA = {
    "DOCUMENTO": "FC - 22118",
    "IDENTIFICACIONEXTERNA": "FC - 22118",
    "COMPROBANTE": "A-0016-00030187",
    "IMPORTEMONTRAN": -707502.73,
}

# Fila real: factura cargada por el otro sistema, que graba
# <CUIT>-<LETRA>-<PTOVTA>-<NUMERO> en IDENTIFICACIONEXTERNA.
FILA_EXTERNA = {
    "DOCUMENTO": "FC - 22219",
    "IDENTIFICACIONEXTERNA": "20313144411-A-0002-00000196",
    "COMPROBANTE": "A-0002-00000196",
    "IMPORTEMONTRAN": -2904000.0,
}


class TestClavesDeSaldo:
    def test_indexa_las_tres_formas_de_nombrar_la_factura(self):
        assert claves_de_fila(FILA_EXTERNA) == {
            normalizar("FC - 22219"),
            normalizar("20313144411-A-0002-00000196"),
            normalizar("A-0002-00000196"),
        }

    def test_ignora_los_campos_vacios(self):
        fila = {**FILA_CLASICA, "IDENTIFICACIONEXTERNA": "", "COMPROBANTE": None}
        assert claves_de_fila(fila) == {normalizar("FC - 22118")}

    def test_las_filas_sin_saldo_no_entran(self):
        saldada = {**FILA_CLASICA, "IMPORTEMONTRAN": 0}
        assert claves_pendientes([saldada]) == {}

    def test_importe_no_numerico_no_rompe(self):
        assert claves_pendientes([{**FILA_CLASICA, "IMPORTEMONTRAN": "s/d"}]) == {}


class TestFiguraConSaldo:
    def test_factura_clasica_por_documento(self):
        pend = claves_pendientes([FILA_CLASICA])
        assert figura_con_saldo(pend, "FC - 22118", "A-0016-00030187")

    def test_factura_del_otro_sistema_matchea_igual(self):
        """Antes se omitía del pago: su IDENTIFICACIONEXTERNA no coincide con nada
        del Excel, y el cruce se hacía sólo contra ese campo."""
        pend = claves_pendientes([FILA_EXTERNA])
        assert figura_con_saldo(pend, "FC - 22219", "A-0002-00000196")

    def test_alcanza_con_el_documento_aunque_el_excel_no_traiga_comprobante(self):
        pend = claves_pendientes([FILA_EXTERNA])
        assert figura_con_saldo(pend, "FC - 22219", "")

    def test_alcanza_con_el_comprobante_si_el_documento_no_pega(self):
        pend = claves_pendientes([FILA_EXTERNA])
        assert figura_con_saldo(pend, "20313144411-A-0002-00000196", "")

    def test_tolera_el_espaciado_del_guion(self):
        pend = claves_pendientes([FILA_CLASICA])
        assert figura_con_saldo(pend, " fc -22118 ", "")

    def test_una_factura_ajena_no_matchea(self):
        pend = claves_pendientes([FILA_EXTERNA])
        assert not figura_con_saldo(pend, "FC - 99999", "A-0002-00099999")

    def test_sin_pendientes_no_matchea_nada(self):
        assert not figura_con_saldo(set(), "FC - 22219", "A-0002-00000196")


class TestIdentificacionExternaConCuit:
    """El CUIT de `IdentificacionExterna` puede venir puntuado de varias formas.

    Las tres son el mismo comprobante. Depender de que el sistema que carga las
    facturas lo mande siempre igual es apoyar el cruce en una convención que
    nadie valida: si un día sale con guiones, la factura se omite del pago.
    """

    CANON = "20313144411-A-0002-00000196"

    def test_sin_puntuacion_queda_igual(self):
        assert normalizar(self.CANON) == self.CANON

    def test_cuit_con_guiones(self):
        assert normalizar("20-31314441-1-A-0002-00000196") == self.CANON

    def test_cuit_con_puntos(self):
        assert normalizar("20.31314441.1-A-0002-00000196") == self.CANON

    def test_letra_en_minuscula(self):
        assert normalizar("20313144411-a-0002-00000196") == self.CANON

    def test_no_toca_los_documentos_normales(self):
        assert normalizar("FC - 21562") == "FC - 21562"
        assert normalizar("FC-21562") == "FC - 21562"
        assert es_fc("FC-21562")

    def test_no_confunde_algo_que_solo_se_parece(self):
        # Menos dígitos de los que lleva un CUIT: no es una identificación externa.
        assert normalizar("2031-A-0002-00000196") != self.CANON

    def test_cruza_aunque_cada_lado_lo_escriba_distinto(self):
        fila = {
            "DOCUMENTO": "",
            "IDENTIFICACIONEXTERNA": "20-31314441-1-A-0002-00000196",
            "COMPROBANTE": "",
            "IMPORTEMONTRAN": -2904000.0,
        }
        assert figura_con_saldo(claves_pendientes([fila]), self.CANON)

    def test_y_tambien_al_reves(self):
        fila = {
            "DOCUMENTO": "",
            "IDENTIFICACIONEXTERNA": self.CANON,
            "COMPROBANTE": "",
            "IMPORTEMONTRAN": -1.0,
        }
        assert figura_con_saldo(
            claves_pendientes([fila]), "20-31314441-1-A-0002-00000196"
        )


class TestIdExterna:
    """`/facturaCompra/{clave}` resuelve por IdentificacionExterna.

    Con el documento interno devuelve 404 para lo que carga el otro sistema, y
    sin ratio se asume 100% gravado: la retención sale de más y al proveedor se
    le paga de menos.
    """

    def test_arma_la_clave(self):
        assert id_externa("20313144411", "A-0002-00000196") == "20313144411-A-0002-00000196"

    def test_limpia_la_puntuacion_del_cuit(self):
        assert id_externa("20-31314441-1", "A-0002-00000196") == "20313144411-A-0002-00000196"

    def test_normaliza_el_comprobante(self):
        assert id_externa("20313144411", "  a-0002-00000196 ") == "20313144411-A-0002-00000196"

    def test_sin_comprobante_no_arma_nada(self):
        assert id_externa("20313144411", "") == ""

    def test_sin_cuit_no_arma_nada(self):
        assert id_externa("", "A-0002-00000196") == ""

    def test_lo_que_arma_es_lo_que_normalizar_canoniza(self):
        # Las dos puntas tienen que coincidir o el cruce de saldos no cierra.
        assert normalizar(id_externa("20-31314441-1", "A-0002-00000196")) == (
            "20313144411-A-0002-00000196"
        )


class TestAplicacionPara:
    """`AplicacionOrigen` resuelve por IdentificacionExterna, no por el documento.

    Verificado contra el ERP: con `FC - 22219` la OP se crea con 200 pero **no
    queda aplicada** — Finnegans lo trata igual que a un documento inexistente.
    La factura sigue con saldo y el control la volvería a ofrecer para pagar.
    """

    def test_factura_de_finnegans_manda_el_documento_de_siempre(self):
        # IdentificacionExterna == DOCUMENTO: el valor no cambia respecto de antes.
        pend = claves_pendientes([FILA_CLASICA])
        assert aplicacion_para(pend, "FC - 22118", "A-0016-00030187") == "FC - 22118"

    def test_factura_del_otro_sistema_manda_la_identificacion_externa(self):
        pend = claves_pendientes([FILA_EXTERNA])
        assert aplicacion_para(pend, "FC - 22219", "A-0002-00000196") == (
            "20313144411-A-0002-00000196"
        )

    def test_resuelve_igual_entrando_por_el_comprobante(self):
        pend = claves_pendientes([FILA_EXTERNA])
        assert aplicacion_para(pend, "", "A-0002-00000196") == (
            "20313144411-A-0002-00000196"
        )

    def test_sin_saldo_consultado_cae_al_documento(self):
        # pendientes = None: la consulta falló. Se manda lo de antes y se avisa.
        assert aplicacion_para(None, "FC - 22219", "A-0002-00000196") == "FC - 22219"

    def test_documento_que_no_esta_en_el_indice_cae_al_documento(self):
        pend = claves_pendientes([FILA_EXTERNA])
        assert aplicacion_para(pend, "FC - 11111", "") == "FC - 11111"

    def test_una_fila_sin_identificacion_externa_cae_al_documento(self):
        fila = {**FILA_CLASICA, "IDENTIFICACIONEXTERNA": ""}
        pend = claves_pendientes([fila])
        assert aplicacion_para(pend, "FC - 22118", "") == "FC - 22118"
