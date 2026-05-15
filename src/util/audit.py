from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_LOCK = threading.Lock()


def audit_log_path() -> Path:
    app_dir = Path(os.environ.get("APPDATA", Path.home())) / "GeneradorDePagos"
    return app_dir / "audit_log.jsonl"


def _sanitize_url(url: str) -> str:
    parts = urlsplit(url)
    query_items = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        if key.upper() == "ACCESS_TOKEN":
            query_items.append((key, "[REDACTED]"))
        else:
            query_items.append((key, value))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query_items), parts.fragment))


def record_http_exchange(
    name: str,
    method: str,
    url: str,
    request_body: Any | None = None,
    response_status: int | None = None,
    response_body: str | None = None,
    error: str | None = None,
) -> None:
    entry: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "name": name,
        "method": method.upper(),
        "url": _sanitize_url(url),
    }
    if request_body is not None:
        entry["request"] = request_body
    if response_status is not None:
        entry["response"] = {
            "status": response_status,
            "body": response_body,
        }
    if error is not None:
        entry["error"] = error

    path = audit_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(entry, ensure_ascii=False, default=str)
    with _LOCK:
        with path.open("a", encoding="utf-8") as fh:
            fh.write(line)
            fh.write("\n")
