#!/usr/bin/env python3
"""Small same-origin JSON API for editable employee-training content."""

from __future__ import annotations

import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import time
from typing import Any
from urllib.request import Request, urlopen

from content_store import ContentStore, ProgressStore


AUTH_URL = os.environ.get(
    "AUTH_URL",
    "https://script.google.com/macros/s/AKfycbyj0Bam_j4rXBV6GnPOTtkzE9IKstFn_TXAq_I8oGEnwywtBWFqiLt0q-QJBruvVZKF/exec",
)
DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
SEED_PATH = Path(os.environ.get("SEED_PATH", "/app/seed/content.json"))
ALLOWED_ORIGIN = os.environ.get("ALLOWED_ORIGIN", "https://academy.analytics-mamasloft.ru")
MAX_BODY = 2 * 1024 * 1024


class UpstreamAuth:
    def __init__(self, url: str) -> None:
        self.url = url
        self.cache: dict[str, tuple[float, dict[str, Any]]] = {}

    def call(self, route: str, **body: Any) -> dict[str, Any]:
        payload = json.dumps({"route": route, **body}, ensure_ascii=False).encode()
        request = Request(self.url, data=payload, headers={"Content-Type": "text/plain"}, method="POST")
        with urlopen(request, timeout=15) as response:
            return json.loads(response.read().decode())

    def authenticate(self, pin: str) -> dict[str, Any]:
        pin = str(pin or "").strip()
        if not pin:
            return {"ok": False, "error": "Требуется PIN"}
        cache_key = hashlib.sha256(pin.encode()).hexdigest()
        cached = self.cache.get(cache_key)
        if cached and cached[0] > time.time():
            return cached[1]
        result = self.call("auth", pin=pin)
        if result.get("ok"):
            safe = {"ok": True, "name": str(result.get("name", "")), "role": str(result.get("role", ""))}
            self.cache[cache_key] = (time.time() + 300, safe)
            return safe
        return {"ok": False, "error": "Неверный PIN"}


CONTENT = ContentStore(DATA_DIR, SEED_PATH)
PROGRESS = ProgressStore(DATA_DIR)
AUTH = UpstreamAuth(AUTH_URL)


def initialize_progress() -> None:
    try:
        legacy = AUTH.call("admin_data")
        if not legacy.get("ok"):
            return
        mapping = {module["topic"]: module["slug"] for module in CONTENT.admin_payload()["modules"]}
        PROGRESS.import_legacy(legacy.get("progress", {}), mapping)
    except Exception as error:
        print(f"Legacy progress import skipped: {type(error).__name__}", flush=True)


def require_user(body: dict[str, Any], admin: bool = False) -> dict[str, Any]:
    user = AUTH.authenticate(str(body.get("pin", "")))
    if not user.get("ok"):
        raise PermissionError("Неверный PIN")
    if admin and user.get("role") != "admin":
        raise PermissionError("Доступ только для администратора")
    return user


def rpc(body: dict[str, Any]) -> dict[str, Any]:
    route = str(body.get("route", ""))
    if route == "content_get":
        return {"ok": True, "modules": CONTENT.public_modules()}

    if route == "progress_get":
        user = require_user(body)
        return {"ok": True, "progress": PROGRESS.get(user["name"])}

    if route in {"progress", "test"}:
        user = require_user(body)
        slug = str(body.get("slug", "")).strip()
        live_slugs = {module["slug"] for module in CONTENT.public_modules()}
        if slug not in live_slugs:
            raise ValueError("Тема не опубликована")
        if route == "progress":
            saved = PROGRESS.mark(user["name"], slug, str(body.get("stage", "")))
        else:
            saved = PROGRESS.mark(user["name"], slug, "quiz", int(body.get("score", 0)))
        return {"ok": True, "progress": saved}

    if route == "admin_data":
        require_user(body, admin=True)
        upstream = AUTH.call("admin_data")
        if not upstream.get("ok"):
            raise RuntimeError("Не удалось получить список сотрудников")
        return {
            "ok": True,
            "users": upstream.get("users", []),
            "modules": CONTENT.public_modules(),
            "progress": PROGRESS.all(),
        }

    if route == "admin_content_get":
        require_user(body, admin=True)
        return {"ok": True, **CONTENT.admin_payload()}

    if route == "admin_mutate":
        user = require_user(body, admin=True)
        payload = CONTENT.mutate(
            action=str(body.get("action", "")),
            raw_module=body.get("module"),
            slug=str(body.get("slug", "")),
            expected_version=int(body.get("version", 0)),
            actor=user["name"],
        )
        return {"ok": True, **payload}

    raise ValueError("Неизвестный запрос")


class Handler(BaseHTTPRequestHandler):
    server_version = "MamaLoftTraining/1.0"

    def _headers(self, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        origin = self.headers.get("Origin", "")
        if origin == ALLOWED_ORIGIN or origin.startswith("http://127.0.0.1:") or origin.startswith("http://localhost:"):
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.end_headers()

    def _send(self, payload: dict[str, Any], status: int = 200) -> None:
        encoded = json.dumps(payload, ensure_ascii=False).encode()
        self._headers(status)
        self.wfile.write(encoded)

    def do_GET(self) -> None:
        if self.path == "/health":
            self._send({"ok": True, "service": "mamasloft-training-api"})
        elif self.path == "/content":
            self._send({"ok": True, "modules": CONTENT.public_modules()})
        else:
            self._send({"ok": False, "error": "Not found"}, 404)

    def do_POST(self) -> None:
        if self.path != "/rpc":
            self._send({"ok": False, "error": "Not found"}, 404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > MAX_BODY:
                raise ValueError("Некорректный размер запроса")
            body = json.loads(self.rfile.read(length).decode())
            self._send(rpc(body))
        except PermissionError as error:
            self._send({"ok": False, "error": str(error)}, 403)
        except (ValueError, TypeError, json.JSONDecodeError) as error:
            self._send({"ok": False, "error": str(error)}, 400)
        except Exception as error:
            print(f"Request failed: {type(error).__name__}", flush=True)
            self._send({"ok": False, "error": "Внутренняя ошибка сервера"}, 500)

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"{self.address_string()} {fmt % args}", flush=True)


if __name__ == "__main__":
    initialize_progress()
    port = int(os.environ.get("PORT", "8080"))
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"Training API listening on {port}", flush=True)
    server.serve_forever()
