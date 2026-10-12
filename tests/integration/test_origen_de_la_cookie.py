"""Con la cookie HttpOnly, un sitio ajeno no puede renovar ni cerrar la sesión de otra persona."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.postgres

BASE = "/api/v1/autenticacion"
ORIGEN_AJENO = "https://sitio-malicioso.example"


@pytest.fixture()
def navegador() -> TestClient:
    if os.getenv("MEDALYZE_TEST_POSTGRES") != "1":
        pytest.skip("Las pruebas PostgreSQL se ejecutan con MEDALYZE_TEST_POSTGRES=1.")
    from app.main import app

    cliente = TestClient(app, raise_server_exceptions=False)
    correo = f"origen-{os.urandom(4).hex()}@ejemplo.mx"
    r = cliente.post(
        f"{BASE}/registro",
        json={
            "nombre_completo": "Dra. Origen",
            "correo": correo,
            "contrasena": "una-contrasena-larga-1",
        },
    )
    assert r.status_code == 201, r.text
    cliente.acceso = r.json()["token_acceso"]  # type: ignore[attr-defined]
    return cliente


def _permitido() -> str:
    from app.core.config import obtener_configuracion

    return obtener_configuracion().cors_origins[0]


def test_la_cookie_no_renueva_desde_un_origen_ajeno(navegador: TestClient) -> None:
    ajeno = navegador.post(f"{BASE}/renovacion", json={}, headers={"Origin": ORIGEN_AJENO})
    assert ajeno.status_code == 401
    assert ajeno.json()["detalle"]["codigo"] == "SIN_AUTENTICACION"
    # El rechazo no consumió el token: el sitio legítimo sigue pudiendo renovar.
    assert (
        navegador.post(f"{BASE}/renovacion", json={}, headers={"Origin": _permitido()}).status_code
        == 200
    )


def test_sin_cabecera_origen_la_renovacion_funciona(navegador: TestClient) -> None:
    assert navegador.post(f"{BASE}/renovacion", json={}).status_code == 200


def test_un_sitio_ajeno_no_puede_cerrar_la_sesion(navegador: TestClient) -> None:
    cabeceras = {"Authorization": f"Bearer {navegador.acceso}", "Origin": ORIGEN_AJENO}  # type: ignore[attr-defined]
    assert navegador.post(f"{BASE}/cierre-sesion", headers=cabeceras).status_code == 401
    # La sesión sigue vigente: no hubo cierre.
    assert navegador.post(f"{BASE}/renovacion", json={}).status_code == 200
