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
