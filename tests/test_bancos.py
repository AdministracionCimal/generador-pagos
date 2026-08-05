"""Nombre del banco (cartera) → código (POST del endoso)."""
from src.api.endpoints import Endpoints
from src.domain.bancos import mapa_por_nombre, normalizar, resolver_codigo

# Nombres y códigos reales de /banco/list.
LISTA = [
    {"codigo": "00017", "nombre": "BBVA BANCO FRANCES S.A."},
    {"codigo": "00034", "nombre": "BANCO PATAGONIA S.A."},
    {"codigo": "00097", "nombre": "BANCO PROVINCIA DEL NEUQUÉN SOCIEDAD ANÓNIMA"},
    {"codigo": "00191", "nombre": "BANCO CREDICOOP COOPERATIVO LIMITADO"},
    {"codigo": "00285", "nombre": "BANCO MACRO S.A."},
]
MAPA = mapa_por_nombre(LISTA)


class TestNormalizar:
    def test_saca_tildes_puntos_y_espacios(self):
        assert normalizar("Banco  Patagonia S.A.") == "BANCOPATAGONIASA"
        assert normalizar("BANCO PROVINCIA DEL NEUQUÉN") == "BANCOPROVINCIADELNEUQUEN"

    def test_las_variantes_de_sa_colapsan_igual(self):
        assert normalizar("BANCO X S.A.") == normalizar("BANCO X S. A.") == normalizar("banco x sa")

    def test_vacio(self):
        assert normalizar(None) == ""
        assert normalizar("   ") == ""


class TestResolverCodigo:
    def test_nombre_tal_como_viene_de_cartera(self):
        """Los nombres coinciden entre el reporte de cartera y /banco/list."""
        assert resolver_codigo(MAPA, "BANCO PATAGONIA S.A.") == "00034"
        assert resolver_codigo(MAPA, "BBVA BANCO FRANCES S.A.") == "00017"
        assert resolver_codigo(MAPA, "BANCO MACRO S.A.") == "00285"

    def test_con_tilde_y_espacios_distintos(self):
        assert resolver_codigo(MAPA, "banco   patagonia  sa") == "00034"
        assert resolver_codigo(
            MAPA, "BANCO PROVINCIA DEL NEUQUEN SOCIEDAD ANONIMA"
        ) == "00097"

    def test_coincidencia_parcial_unica(self):
        assert resolver_codigo(MAPA, "BANCO PROVINCIA DEL NEUQUEN") == "00097"

    def test_no_adivina_si_hay_ambiguedad(self):
        """Dos bancos que empiezan igual no se resuelven: mejor mandar el pago a
        carga manual que endosar con el banco equivocado."""
        mapa = mapa_por_nombre([
            {"codigo": "00001", "nombre": "BANCO DEL SUR S.A."},
            {"codigo": "00002", "nombre": "BANCO DEL SUR PATAGONICO S.A."},
        ])
        assert resolver_codigo(mapa, "BANCO DEL SUR") is None

    def test_banco_desconocido(self):
        assert resolver_codigo(MAPA, "BANCO QUE NO EXISTE") is None
        assert resolver_codigo(MAPA, "") is None


def test_url_del_listado():
    url = Endpoints("https://api.finneg.com/api").banco_list("TOK")
    assert url == "https://api.finneg.com/api/banco/list?ACCESS_TOKEN=TOK"
