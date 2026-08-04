"""Actualización de la app desde el release «latest» de GitHub.

El release usa un tag fijo, así que la fecha del asset no sirve para comparar:
el CI publica el binario un par de minutos **después** de compilarlo, y eso haría
que la app avise de una "versión nueva" que es la que ya tiene. La comparación se
hace por **commit**: el body del release lo declara y el CI lo estampa en
`version.py`.

Reemplazar el `.exe` en Windows tiene una vuelta: el archivo en ejecución está
bloqueado por el propio proceso. Por eso se descarga con otro nombre y el swap lo
hace un `.cmd` que espera a que la app cierre. Las rutas viajan como argumentos
—no incrustadas en el script— para no depender de la codificación del `.cmd`.
"""
from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import httpx

from src.version import BUILD_SHA

_API_RELEASE = (
    "https://api.github.com/repos/AdministracionCimal/generador-pagos/releases/latest"
)
_NOMBRE_ASSET     = "GeneradorDePagos.exe"
_NOMBRE_DESCARGA  = "GeneradorDePagos.nuevo.exe"
NOMBRE_BACKUP     = "GeneradorDePagos.anterior.exe"
NOMBRE_SCRIPT     = "actualizar_generador_de_pagos.cmd"

_RE_COMMIT  = re.compile(r"commit[:\s]+`?([0-9a-f]{7,40})`?", re.I)
_RE_VERSION = re.compile(r"versi[oó]n[:\s]+v?(\d+\.\d+\.\d+)", re.I)


class ActualizacionError(Exception):
    pass


@dataclass
class Actualizacion:
    version: str          # "1.1.0" si el release la declara, o ""
    commit: str
    fecha: datetime | None
    url: str
    sha256: str
    tamanio: int

    def descripcion(self) -> str:
        partes = []
        if self.version:
            partes.append(f"versión {self.version}")
        if self.commit:
            partes.append(f"commit {self.commit[:7]}")
        if self.fecha is not None:
            partes.append(f"publicada el {self.fecha.strftime('%d/%m/%Y')}")
        return " · ".join(partes) or "versión nueva"


# ── comparación (puro, testeable) ─────────────────────────────────────────

def hay_novedad(commit_remoto: str, commit_local: str = BUILD_SHA) -> bool:
    """True si el release salió de otro commit que este build.

    Sin commit local (build de desarrollo) o sin commit remoto no se reporta
    nada: es preferible no avisar que avisar de más.
    """
    if not commit_local or not commit_remoto:
        return False
    remoto, local = commit_remoto.strip().lower(), commit_local.strip().lower()
    # El body puede declarar el sha corto y version.py el largo: se compara el
    # prefijo común. Con menos de 7 caracteres no hay con qué decidir.
    largo = min(len(remoto), len(local))
    if largo < 7:
        return False
    return remoto[:largo] != local[:largo]


def leer_release(payload: dict) -> Actualizacion | None:
    """Traduce la respuesta de la API de GitHub. None si no tiene el asset."""
    asset = next(
        (a for a in payload.get("assets", []) if a.get("name") == _NOMBRE_ASSET),
        None,
    )
    if asset is None or not asset.get("browser_download_url"):
        return None

    body = payload.get("body") or ""
    commit = _RE_COMMIT.search(body)
    version = _RE_VERSION.search(body)
    digest = str(asset.get("digest") or "")

    return Actualizacion(
        version=version.group(1) if version else "",
        commit=commit.group(1) if commit else "",
        fecha=_parsear_fecha(asset.get("updated_at")),
        url=asset["browser_download_url"],
        sha256=digest.removeprefix("sha256:").strip().lower(),
        tamanio=int(asset.get("size") or 0),
    )


def _parsear_fecha(iso: str | None) -> datetime | None:
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


# ── consulta ──────────────────────────────────────────────────────────────

def consultar(timeout: float = 10.0) -> Actualizacion | None:
    """Pide el release a GitHub. Propaga la excepción si falla la red."""
    resp = httpx.get(
        _API_RELEASE,
        headers={"Accept": "application/vnd.github+json"},
        timeout=timeout,
        follow_redirects=True,
    )
    resp.raise_for_status()
    return leer_release(resp.json())


# ── descarga y reemplazo ──────────────────────────────────────────────────

def exe_actual() -> Path | None:
    """Ruta del .exe compilado, o None si corre desde el código fuente."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve()
    return None


def descargar(actu: Actualizacion, destino: Path, progreso=None) -> Path:
    """Descarga verificando el sha256 que publica el release.

    `progreso(bajado, total)` se llama durante la descarga. Si el hash no
    coincide, borra el archivo: nunca se reemplaza el .exe con algo no verificado.
    """
    sha = hashlib.sha256()
    bajado = 0
    try:
        with httpx.stream("GET", actu.url, follow_redirects=True, timeout=60.0) as resp:
            resp.raise_for_status()
            with destino.open("wb") as fh:
                for chunk in resp.iter_bytes(256 * 1024):
                    fh.write(chunk)
                    sha.update(chunk)
                    bajado += len(chunk)
                    if progreso is not None:
                        progreso(bajado, actu.tamanio)
    except Exception as exc:
        destino.unlink(missing_ok=True)
        raise ActualizacionError(f"No se pudo descargar la actualización: {exc}") from exc

    if actu.sha256 and sha.hexdigest() != actu.sha256:
        destino.unlink(missing_ok=True)
        raise ActualizacionError(
            "El archivo descargado no coincide con el del release "
            "(verificación sha256 fallida). No se actualizó nada."
        )
    return destino


ESPERA_MAX_INTENTOS = 120   # ~2 minutos: si la app no cierra, se rinde sin tocar nada


def script_de_swap() -> str:
    """Contenido del `.cmd` que reemplaza el binario.

    Recibe todo por argumentos: %1 PID a esperar, %2 exe actual, %3 exe nuevo,
    %4 backup, %5 relanzar (1/0). Así el script queda ASCII puro y no importa si
    las rutas tienen acentos o espacios.

    Dos cuidados que parecen paranoia y no lo son:

    - `tasklist`, `findstr` y `ping` se llaman con **ruta absoluta**. Si se
      resolvieran por PATH, un `find`/`findstr` de otra herramienta (Git, por
      ejemplo) devuelve error, el loop cree que la app ya cerró y reemplaza el
      binario con la app abierta.
    - nada de bloques `( )` alrededor del contador: dentro de un bloque, `%VAR%`
      se expande al parsear y el contador quedaría siempre en 0.
    """
    return "\r\n".join([
        "@echo off",
        "setlocal",
        'set "PID=%~1"',
        'set "ACTUAL=%~2"',
        'set "NUEVO=%~3"',
        'set "BACKUP=%~4"',
        'set "RELANZAR=%~5"',
        'set "SYS=%SystemRoot%\\System32"',
        'for %%F in ("%ACTUAL%") do set "NOMBRE=%%~nxF"',
        "set /a INTENTOS=0",
        "",
        ":esperar",
        '"%SYS%\\tasklist.exe" /FI "PID eq %PID%" /NH 2>nul | '
        '"%SYS%\\findstr.exe" /I /C:"%NOMBRE%" >nul',
        "if errorlevel 1 goto reemplazar",
        "set /a INTENTOS+=1",
        f"if %{'INTENTOS'}% GEQ {ESPERA_MAX_INTENTOS} goto rendirse",
        '"%SYS%\\ping.exe" -n 2 127.0.0.1 >nul',
        "goto esperar",
        "",
        ":reemplazar",
        'if exist "%BACKUP%" del /q "%BACKUP%"',
        'copy /y "%ACTUAL%" "%BACKUP%" >nul',
        'move /y "%NUEVO%" "%ACTUAL%" >nul',
        "if errorlevel 1 goto fallo",
        'if "%RELANZAR%"=="1" start "" "%ACTUAL%"',
        "exit /b 0",
        "",
        ":rendirse",
        'del /q "%NUEVO%" 2>nul',
        "exit /b 2",
        "",
        ":fallo",
        'if exist "%BACKUP%" copy /y "%BACKUP%" "%ACTUAL%" >nul',
        'del /q "%NUEVO%" 2>nul',
        "exit /b 1",
        "",
    ])


def aplicar(actu: Actualizacion, progreso=None) -> None:
    """Descarga, verifica y lanza el swap. Al volver, hay que cerrar la app.

    No reemplaza nada por sí misma: deja el `.cmd` corriendo, que espera a que
    este proceso termine. Si algo falla antes, levanta `ActualizacionError` y el
    `.exe` actual queda intacto.
    """
    exe = exe_actual()
    if exe is None:
        raise ActualizacionError(
            "La actualización automática sólo funciona en el .exe compilado."
        )
    if not os.access(exe.parent, os.W_OK):
        raise ActualizacionError(
            f"No hay permiso de escritura en {exe.parent}. Descargá el .exe a mano "
            f"o mové la aplicación a una carpeta propia."
        )

    nuevo = exe.with_name(_NOMBRE_DESCARGA)
    descargar(actu, nuevo, progreso)

    script = Path(tempfile.gettempdir()) / NOMBRE_SCRIPT
    script.write_text(script_de_swap(), encoding="ascii")

    subprocess.Popen(
        [
            "cmd", "/c", str(script),
            str(os.getpid()), str(exe), str(nuevo), str(exe.with_name(NOMBRE_BACKUP)), "1",
        ],
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        close_fds=True,
    )
