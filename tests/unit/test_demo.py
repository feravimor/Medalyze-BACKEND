from fastapi import Response

from app.api.rutas.autenticacion import _establecer_cookie, _respuesta_sesion
from app.api.rutas.demo import EXTRAS, SCENARIOS
from app.core.config import obtener_configuracion


def test_demo_has_the_five_documented_scenarios() -> None:
    assert list(SCENARIOS) == ["consulta", "limpieza", "resina", "extraccion", "ortodoncia"]
    assert [SCENARIOS[key]["insumos"] for key in SCENARIOS] == [15, 18, 26, 17, 30]
    assert [SCENARIOS[key]["precio"] for key in SCENARIOS] == [
        "650.00",
        "1200.00",
        "2550.00",
        "1050.00",
        "1250.00",
    ]


def test_demo_catalog_includes_centimeter_consumables() -> None:
    assert {item[2] for item in EXTRAS["ortodoncia"] if "cm" in item[0]} == {"CM"}


def test_normal_session_has_false_guest_mode() -> None:
    respuesta = _respuesta_sesion(
        {
            "usuario_id": "usuario",
            "nombre_completo": "Usuario",
            "correo": "usuario@example.com",
            "rol": "PROPIETARIO",
            "organizacion_id": "organizacion",
            "nombre_comercial": "Consultorio",
            "codigo_moneda": "MXN",
            "multiplo_redondeo": 50,
            "espaciado_por_defecto": 10,
            "organizacion_revision": 0,
            "onboarding_completado": False,
        },
        "token",
        900,
        {},
    )
    assert respuesta["modo_invitado"] is False
    assert "escenario" not in respuesta
    assert "expira_en" not in respuesta


def test_guest_session_preserves_demo_fields() -> None:
    escenario = {"clave": "consulta"}
    respuesta = _respuesta_sesion(
        {
            "usuario_id": "usuario",
            "nombre_completo": "Usuario demo 1",
            "correo": "demo@example.com",
            "rol": "PROPIETARIO",
            "organizacion_id": "organizacion",
            "nombre_comercial": "DEMO Consulta",
            "codigo_moneda": "MXN",
            "multiplo_redondeo": 50,
            "espaciado_por_defecto": 10,
            "organizacion_revision": 0,
            "onboarding_completado": True,
            "modo_invitado": True,
            "escenario": escenario,
            "expira_en": "2026-10-13T12:00:00+00:00",
        },
        "token",
        900,
        {},
    )
    assert respuesta["modo_invitado"] is True
    assert respuesta["escenario"] == escenario
    assert respuesta["expira_en"] == "2026-10-13T12:00:00+00:00"


def test_normal_cookie_keeps_configured_duration() -> None:
    response = Response()
    _establecer_cookie(response, "normal")
    assert (
        f"Max-Age={obtener_configuracion().refresh_ttl_days * 24 * 60 * 60}"
        in response.headers["set-cookie"]
    )


def test_guest_cookie_is_limited_to_24_hours() -> None:
    response = Response()
    _establecer_cookie(response, "guest", 24 * 60 * 60)
    assert "Max-Age=86400" in response.headers["set-cookie"]
