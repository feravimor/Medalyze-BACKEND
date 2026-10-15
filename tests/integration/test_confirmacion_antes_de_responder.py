"""Las escrituras se confirman en la base de datos ANTES de que el cliente reciba la respuesta.

Si el ``commit`` ocurre después de enviarla, quien pide el recurso recién creado puede recibir 404 o datos
viejos. Pasa más cuanto más lenta es la base de datos (PostgreSQL en Docker Desktop, una base remota).
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.privacidad import VERSION_AVISO_PRIVACIDAD_VIGENTE

RAIZ = Path(__file__).resolve().parents[2]


def test_ningun_endpoint_usa_la_sesion_protegida_con_el_alcance_por_defecto() -> None:
    usos = 0
    for ruta in sorted((RAIZ / "app" / "api" / "rutas").glob("*.py")):
        for coincidencia in re.finditer(
            r"Depends\(\s*obtener_sesion_protegida\s*([^)]*)\)", ruta.read_text(encoding="utf-8")
        ):
            usos += 1
            assert 'scope="function"' in coincidencia.group(1), (
                f'{ruta.name}: falta scope="function" ({coincidencia.group(0)})'
            )
    assert usos > 40  # los endpoints protegidos existen: la búsqueda no está vacía


@pytest.mark.postgres
def test_el_commit_ocurre_antes_de_enviar_la_respuesta(monkeypatch: pytest.MonkeyPatch) -> None:
    if os.getenv("MEDALYZE_TEST_POSTGRES") != "1":
        pytest.skip("Las pruebas PostgreSQL se ejecutan con MEDALYZE_TEST_POSTGRES=1.")
    from app.main import app

    cliente = TestClient(app, raise_server_exceptions=False)
    r = cliente.post(
        "/api/v1/autenticacion/registro",
        json={
            "nombre_completo": "Dra. Orden",
            "correo": f"orden-{os.urandom(4).hex()}@ejemplo.mx",
            "contrasena": "una-contrasena-larga-1",
            "acepta_aviso_privacidad": True,
            "version_aviso_privacidad": VERSION_AVISO_PRIVACIDAD_VIGENTE,
        },
    )
    assert r.status_code == 201, r.text
    token = r.json()["token_acceso"]

    eventos: list[str] = []
    original = Session.commit

    def commit_registrado(self: Session) -> None:
        eventos.append("commit")
        original(self)

    monkeypatch.setattr(Session, "commit", commit_registrado)

    async def llamar() -> int:
        cuerpo = json.dumps(
            {"nombre": "Orden", "especialidad": "GENERAL", "duracion_clinica": 30}
        ).encode()
        enviado = False
        estado = 0

        async def receive() -> dict[str, Any]:
            nonlocal enviado
            if not enviado:
                enviado = True
                return {"type": "http.request", "body": cuerpo, "more_body": False}
            return {"type": "http.disconnect"}

        async def send(mensaje: dict[str, Any]) -> None:
            nonlocal estado
            if mensaje["type"] == "http.response.start":
                estado = mensaje["status"]
                eventos.append("respuesta")

        cabeceras = [
            (b"host", b"testserver"), (b"content-type", b"application/json"),
            (b"authorization", f"Bearer {token}".encode()),
            (b"idempotency-key", f"orden-{os.urandom(8).hex()}".encode()),
        ]  # fmt: skip
        alcance = {
            "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "POST", "scheme": "http",
            "path": "/api/v1/tratamientos", "raw_path": b"/api/v1/tratamientos", "query_string": b"", "root_path": "",
            "headers": cabeceras, "client": ("127.0.0.1", 50000), "server": ("testserver", 80),
        }  # fmt: skip
        await app(alcance, receive, send)
        return estado

    assert asyncio.run(llamar()) == 201
    assert "commit" in eventos and "respuesta" in eventos
    assert eventos.index("commit") < eventos.index("respuesta"), (
        f"la respuesta salió antes de confirmar la transacción: {eventos}"
    )
