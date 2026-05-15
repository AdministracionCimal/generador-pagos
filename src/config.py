import json
import os
from pathlib import Path

from cryptography.fernet import Fernet

_APP_DIR = Path(os.environ.get("APPDATA", Path.home())) / "GeneradorDePagos"
_CONFIG_PATH = _APP_DIR / "config.enc"
_KEY_PATH = _APP_DIR / "key.bin"

_DEFAULTS: dict = {
    "base_url": "https://api.finneg.com/api",
    "client_id": "",
    "client_secret": "",
    "empresa_codigo": "EMPRE01",
    "empresa_nombre": "EMPRE01",
    "chequera_codigo": "",
    "chequera_ultimo": "",
    "chequera_limite": "",
    "cuenta_banco_codigo": "02.01.04.01.0009",
    "cuenta_banco_nombre": "02.01.04.01.0009",
    "cuenta_banco_transferencia_codigo": "01.01.01.02.0006",
    "cuenta_banco_transferencia_nombre": "01.01.01.02.0006",
    "banco_codigo": "00285",
    "talonario_op_codigo": "TE-OP",
    "op_bancaria_cheque_codigo": "EMCHPROP",
    "op_bancaria_cheque_nombre": "Emisión de cheque propio",
    "op_bancaria_transferencia_codigo": "TLote",
    "op_bancaria_transferencia_nombre": "Transferencia por Lote",
    "cotizacion_dolar": "",
}


def _ensure_key() -> Fernet:
    _APP_DIR.mkdir(parents=True, exist_ok=True)
    if not _KEY_PATH.exists():
        _KEY_PATH.write_bytes(Fernet.generate_key())
        _KEY_PATH.chmod(0o600)
    return Fernet(_KEY_PATH.read_bytes())


def load() -> dict:
    f = _ensure_key()
    if not _CONFIG_PATH.exists():
        return dict(_DEFAULTS)
    try:
        data = json.loads(f.decrypt(_CONFIG_PATH.read_bytes()).decode())
        return {**_DEFAULTS, **data}
    except Exception:
        return dict(_DEFAULTS)


def save(cfg: dict) -> None:
    f = _ensure_key()
    _CONFIG_PATH.write_bytes(f.encrypt(json.dumps(cfg).encode()))


_REQUIRED_FIELDS = {
    "base_url":      "URL de la API",
    "client_id":     "Client ID",
    "client_secret": "Client Secret",
}


def is_configured(cfg: dict) -> bool:
    return all(cfg.get(k) for k in _REQUIRED_FIELDS)


def missing_fields(cfg: dict) -> list[str]:
    """Devuelve los nombres legibles de los campos requeridos que faltan."""
    return [label for key, label in _REQUIRED_FIELDS.items() if not cfg.get(key)]
