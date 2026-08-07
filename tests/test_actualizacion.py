"""Detección de versión nueva y armado del reemplazo del .exe."""
from datetime import datetime, timezone

import pytest

from pathlib import Path

from src.util.actualizacion import (
    ESPERA_MAX_INTENTOS,
    SUFIJO_BACKUP,
    SUFIJO_DESCARGA,
    ActualizacionError,
    descargar,
    entorno_limpio,
    hay_novedad,
    leer_release,
    ruta_hermana,
    script_de_swap,
)

SHA_VIEJO = "7a841b9a48a5fd59dedc03aa11223344556677889"
SHA_NUEVO = "abcdef1234567890abcdef1234567890abcdef12"


def _release(body: str = "", **asset) -> dict:
    base = {
        "name": "GeneradorDePagos.exe",
        "browser_download_url": "https://example.test/GeneradorDePagos.exe",
        "updated_at": "2026-08-03T18:36:55Z",
        "size": 45528206,
        "digest": "sha256:5973bc7b94f618e802ccc3c74f49e5af11358ffd46d8eedf48d7605a0103cbb4",
    }
    base.update(asset)
    return {"body": body, "assets": [base]}


class TestHayNovedad:
    def test_otro_commit_es_novedad(self):
        assert hay_novedad(SHA_NUEVO, SHA_VIEJO)

    def test_mismo_commit_no_es_novedad(self):
        assert not hay_novedad(SHA_VIEJO, SHA_VIEJO)

    def test_compara_por_prefijo(self):
        """El body puede traer el sha corto y version.py el largo."""
        assert not hay_novedad(SHA_VIEJO[:7], SHA_VIEJO)

    def test_ignora_mayusculas(self):
        assert not hay_novedad(SHA_VIEJO.upper(), SHA_VIEJO)

    def test_build_local_no_chequea(self):
        """Sin BUILD_SHA (compilado a mano) no se avisa de nada."""
        assert not hay_novedad(SHA_NUEVO, "")

    def test_release_sin_commit_no_avisa(self):
        """Fail-closed: mejor no avisar que avisar de una version que no se puede
        comparar."""
        assert not hay_novedad("", SHA_VIEJO)


class TestLeerRelease:
    def test_extrae_todo_del_payload(self):
        actu = leer_release(_release(
            body=f"Versión: 1.2.0 · commit: `{SHA_NUEVO}`"
        ))
        assert actu.version == "1.2.0"
        assert actu.commit == SHA_NUEVO
        assert actu.url.endswith("GeneradorDePagos.exe")
        assert actu.sha256.startswith("5973bc7b")   # sin el prefijo "sha256:"
        assert actu.tamanio == 45528206
        assert actu.fecha == datetime(2026, 8, 3, 18, 36, 55, tzinfo=timezone.utc)

    def test_lee_el_formato_viejo_del_body(self):
        """Los releases anteriores decían «desde el commit `sha`»."""
        actu = leer_release(_release(body=f"Compilado desde el commit `{SHA_NUEVO}`"))
        assert actu.commit == SHA_NUEVO
        assert actu.version == ""

    def test_sin_el_asset_devuelve_none(self):
        assert leer_release({"body": "", "assets": [{"name": "otra-cosa.zip"}]}) is None
        assert leer_release({"body": "", "assets": []}) is None

    def test_sin_digest_no_falla(self):
        actu = leer_release(_release(digest=None))
        assert actu.sha256 == ""

    def test_fecha_invalida_no_rompe(self):
        assert leer_release(_release(updated_at="ayer")).fecha is None

    def test_descripcion_legible(self):
        actu = leer_release(_release(body=f"Versión: 1.2.0 · commit: `{SHA_NUEVO}`"))
        desc = actu.descripcion()
        assert "1.2.0" in desc and "03/08/2026" in desc


class TestScriptDeSwap:
    def test_espera_al_proceso_antes_de_reemplazar(self):
        s = script_de_swap()
        assert "tasklist" in s
        assert ":esperar" in s
        assert s.index(":esperar") < s.index("move /y")

    def test_hace_backup_y_restaura_si_falla(self):
        s = script_de_swap()
        assert 'copy /y "%ACTUAL%" "%BACKUP%"' in s
        assert ":fallo" in s
        assert 'copy /y "%BACKUP%" "%ACTUAL%"' in s

    def test_todo_por_argumentos_sin_rutas_incrustadas(self):
        """Las rutas viajan como %1..%5 para no depender de la codificación
        del .cmd (acentos en la ruta del usuario)."""
        s = script_de_swap()
        for arg in ("%~1", "%~2", "%~3", "%~4", "%~5"):
            assert arg in s
        assert s.isascii()

    def test_relanzar_es_opcional(self):
        assert 'if "%RELANZAR%"=="1" start "" "%ACTUAL%"' in script_de_swap()

    def test_herramientas_del_sistema_con_ruta_absoluta(self):
        """Si se resolvieran por PATH, un findstr/find de otra herramienta (Git,
        por ejemplo) devuelve error, el loop cree que la app cerró y reemplaza el
        binario en uso. Pasó de verdad al probarlo."""
        s = script_de_swap()
        for herramienta in ("tasklist.exe", "findstr.exe", "ping.exe"):
            assert f'"%SYS%\\{herramienta}"' in s, herramienta
        assert 'set "SYS=%SystemRoot%\\System32"' in s

    def test_espera_a_todos_los_procesos_no_solo_al_pid(self):
        """El .exe onefile corre como dos procesos: esperar sólo al PID deja al
        bootloader padre todavía con el archivo abierto."""
        s = script_de_swap()
        assert ":esperar_todas" in s
        assert 'IMAGENAME eq %NOMBRE%' in s
        assert s.index(":esperar_todas") < s.index(":reemplazar")

    def test_deja_margen_antes_de_relanzar(self):
        s = script_de_swap()
        reemplazo = s[s.index(":reemplazar"):s.index("exit /b 0")]
        assert reemplazo.index("move /y") < reemplazo.index("ping.exe")
        assert reemplazo.index("ping.exe") < reemplazo.index("start")

    def test_se_rinde_si_la_app_no_cierra(self):
        s = script_de_swap()
        assert f"GEQ {ESPERA_MAX_INTENTOS} goto rendirse" in s
        assert ":rendirse" in s
        # Al rendirse limpia la descarga y no toca el .exe en uso.
        rendirse = s[s.index(":rendirse"):]
        assert 'del /q "%NUEVO%"' in rendirse
        assert "move" not in rendirse

    def test_contador_sin_bloques_de_parentesis(self):
        """Dentro de un bloque `( )` batch expande %VAR% al parsear y el contador
        quedaría siempre en 0."""
        for linea in script_de_swap().splitlines():
            assert not linea.strip().endswith("("), linea


class TestDescargar:
    def test_hash_que_no_coincide_borra_el_archivo(self, tmp_path, monkeypatch):
        import src.util.actualizacion as mod

        class _RespFalsa:
            def raise_for_status(self): pass
            def iter_bytes(self, _n): yield b"contenido que no es el del release"
            def __enter__(self): return self
            def __exit__(self, *a): return False

        monkeypatch.setattr(mod.httpx, "stream", lambda *a, **k: _RespFalsa())
        actu = leer_release(_release())          # digest del release real
        destino = tmp_path / "nuevo.exe"

        with pytest.raises(ActualizacionError, match="sha256"):
            descargar(actu, destino)
        assert not destino.exists()

    def test_hash_correcto_deja_el_archivo(self, tmp_path, monkeypatch):
        import hashlib

        import src.util.actualizacion as mod

        contenido = b"binario de prueba"
        digest = hashlib.sha256(contenido).hexdigest()

        class _RespOk:
            def raise_for_status(self): pass
            def iter_bytes(self, _n): yield contenido
            def __enter__(self): return self
            def __exit__(self, *a): return False

        monkeypatch.setattr(mod.httpx, "stream", lambda *a, **k: _RespOk())
        actu = leer_release(_release(digest=f"sha256:{digest}"))
        destino = tmp_path / "nuevo.exe"

        vistos: list[tuple[int, int]] = []
        descargar(actu, destino, progreso=lambda b, t: vistos.append((b, t)))

        assert destino.read_bytes() == contenido
        assert vistos == [(len(contenido), actu.tamanio)]


class TestEntornoDelActualizador:
    """El bug real de la primera actualización: el .exe nuevo heredaba la carpeta
    temporal del proceso viejo y moria con «Failed to load Python DLL»."""

    def test_saca_las_variables_de_pyinstaller(self):
        sucio = {
            "PATH": "C:\\Windows",
            "_MEIPASS2": "C:\\Users\\x\\AppData\\Local\\Temp\\_MEI113162\\",
            "_PYI_ARCHIVE_FILE": "C:\\app\\GeneradorDePagos.exe",
            "_PYI_APPLICATION_HOME_DIR": "C:\\Temp\\_MEI113162",
        }
        limpio = entorno_limpio(sucio)
        assert limpio == {"PATH": "C:\\Windows"}

    def test_conserva_el_resto_del_entorno(self):
        sucio = {"APPDATA": "C:\\Users\\x\\AppData\\Roaming", "TEMP": "C:\\Temp"}
        assert entorno_limpio(sucio) == sucio

    def test_no_le_pasa_variables_de_pyinstaller_al_proceso_hijo(self, monkeypatch):
        monkeypatch.setenv("_MEIPASS2", "C:\\Temp\\_MEI999")
        assert "_MEIPASS2" not in entorno_limpio()


class TestNombresDerivadosDelExe:
    """El programa puede tener otro nombre: el de Cimalco se llama
    «Generador De Pagos.exe», con espacios. El backup y la descarga se derivan de
    ese nombre para que se reconozcan al lado del original."""

    def test_backup_junto_al_exe_con_su_nombre(self):
        exe = Path(r"C:\GeneradorDePagos\Generador De Pagos.exe")
        assert ruta_hermana(exe, SUFIJO_BACKUP).name == "Generador De Pagos.anterior.exe"

    def test_descarga_junto_al_exe_con_su_nombre(self):
        exe = Path(r"C:\app\GeneradorDePagos.exe")
        assert ruta_hermana(exe, SUFIJO_DESCARGA).name == "GeneradorDePagos.nuevo.exe"

    def test_queda_en_la_misma_carpeta(self):
        exe = Path(r"D:\Programas\App.exe")
        assert ruta_hermana(exe, SUFIJO_BACKUP).parent == exe.parent

    def test_los_sufijos_son_reconocibles(self):
        assert "anterior" in SUFIJO_BACKUP
        assert "nuevo" in SUFIJO_DESCARGA
