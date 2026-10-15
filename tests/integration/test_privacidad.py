import os
import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text

from app.core.privacidad import VERSION_AVISO_PRIVACIDAD_VIGENTE
from app.core.seguridad import hash_contrasena

pytestmark = pytest.mark.postgres


@pytest.fixture(scope="module")
def admin() -> Iterator[Engine]:
    if os.getenv("MEDALYZE_TEST_POSTGRES") != "1":
        pytest.skip("Las pruebas PostgreSQL se ejecutan con MEDALYZE_TEST_POSTGRES=1.")
    motor = create_engine(os.environ["ALEMBIC_DATABASE_URL"], pool_pre_ping=True)
    yield motor
    motor.dispose()


@pytest.fixture(scope="module")
def cliente(admin: Engine) -> TestClient:
    from app.main import app

    return TestClient(app, raise_server_exceptions=False)


def _correo(prefijo: str) -> str:
    return f"{prefijo}-{uuid.uuid4().hex[:12]}@ejemplo.mx"


def _crear_usuario_pendiente(admin: Engine, correo: str) -> tuple[str, str]:
    with admin.begin() as conexion:
        usuario = conexion.scalar(
            text("""
                INSERT INTO usuario_plataforma (correo, hash_contrasena, nombre_completo)
                VALUES (:correo, :hash, 'Usuario QA pendiente') RETURNING identificador
            """),
            {"correo": correo, "hash": hash_contrasena("una-contrasena-larga-1")},
        )
        organizacion = conexion.scalar(
            text(
                "INSERT INTO organizacion_consultorio (nombre_comercial) VALUES ('QA privacidad') RETURNING identificador"
            )
        )
        conexion.execute(
            text("""
                INSERT INTO membresia_usuario_en_organizacion
                  (identificador_usuario, identificador_organizacion, rol)
                VALUES (:usuario, :organizacion, 'PROPIETARIO')
            """),
            {"usuario": usuario, "organizacion": organizacion},
        )
    return str(usuario), str(organizacion)


def test_registros_sin_aceptacion_no_dejan_persistencia(cliente: TestClient, admin: Engine) -> None:
    for acepta, version, codigo in (
        (False, VERSION_AVISO_PRIVACIDAD_VIGENTE, "AVISO_PRIVACIDAD_REQUERIDO"),
        (True, "1900-01-01", "VERSION_AVISO_PRIVACIDAD_INVALIDA"),
    ):
        correo = _correo("registro-invalido")
        respuesta = cliente.post(
            "/api/v1/autenticacion/registro",
            json={
                "nombre_completo": "Registro inválido",
                "correo": correo,
                "contrasena": "una-contrasena-larga-1",
                "acepta_aviso_privacidad": acepta,
                "version_aviso_privacidad": version,
            },
        )
        assert respuesta.status_code == 422
        assert respuesta.json()["detalle"]["codigo"] == codigo
        with admin.connect() as conexion:
            assert conexion.scalar(
                text("SELECT 1 FROM usuario_plataforma WHERE correo=:correo"),
                {"correo": correo},
            ) is None


def test_registro_valido_persiste_una_aceptacion(cliente: TestClient, admin: Engine) -> None:
    correo = _correo("registro-valido")
    respuesta = cliente.post(
        "/api/v1/autenticacion/registro",
        json={
            "nombre_completo": "Registro válido",
            "correo": correo,
            "contrasena": "una-contrasena-larga-1",
            "acepta_aviso_privacidad": True,
            "version_aviso_privacidad": VERSION_AVISO_PRIVACIDAD_VIGENTE,
        },
    )
    assert respuesta.status_code == 201
    cuerpo = respuesta.json()
    estado = cuerpo["aviso_privacidad"]
    assert estado["version_aceptada"] == VERSION_AVISO_PRIVACIDAD_VIGENTE
    assert estado["requiere_aceptar"] is False
    assert estado["aceptado_en"].endswith("+00:00")
    with admin.connect() as conexion:
        assert conexion.scalar(
            text("""
                SELECT count(*) FROM aceptacion_aviso_privacidad a
                JOIN usuario_plataforma u ON u.identificador=a.identificador_usuario
                WHERE u.correo=:correo AND a.version_aviso=:version
            """),
            {"correo": correo, "version": VERSION_AVISO_PRIVACIDAD_VIGENTE},
        ) == 1


def test_usuario_existente_pendiente_acepta_sin_duplicar(
    cliente: TestClient, admin: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    correo = _correo("pendiente")
    usuario, _ = _crear_usuario_pendiente(admin, correo)
    inicio = cliente.post(
        "/api/v1/autenticacion/inicio-sesion",
        json={"correo": correo, "contrasena": "una-contrasena-larga-1"},
    )
    assert inicio.status_code == 200
    token = inicio.json()["token_acceso"]
    assert inicio.json()["aviso_privacidad"]["requiere_aceptar"] is True
    renovacion = cliente.post("/api/v1/autenticacion/renovacion", json={})
    assert renovacion.status_code == 200
    assert renovacion.json()["aviso_privacidad"]["requiere_aceptar"] is True
    encabezados = {"Authorization": f"Bearer {token}", "Idempotency-Key": uuid.uuid4().hex}
    cuerpo = {
        "acepta_aviso_privacidad": True,
        "version_aviso_privacidad": VERSION_AVISO_PRIVACIDAD_VIGENTE,
    }
    aceptacion = cliente.post(
        "/api/v1/cuenta/aviso-privacidad/aceptacion", json=cuerpo, headers=encabezados
    )
    assert aceptacion.status_code == 200
    repetida = cliente.post(
        "/api/v1/cuenta/aviso-privacidad/aceptacion", json=cuerpo, headers=encabezados
    )
    assert repetida.status_code == 200
    assert repetida.json() == aceptacion.json()
    actual = cliente.get("/api/v1/autenticacion/usuario-actual", headers=encabezados)
    assert actual.status_code == 200
    assert actual.json()["aviso_privacidad"]["requiere_aceptar"] is False
    with admin.connect() as conexion:
        assert conexion.scalar(
            text("""
                SELECT count(*) FROM aceptacion_aviso_privacidad
                WHERE identificador_usuario=:usuario AND version_aviso=:version
            """),
            {"usuario": usuario, "version": VERSION_AVISO_PRIVACIDAD_VIGENTE},
        ) == 1
    conflicto = cliente.post(
        "/api/v1/cuenta/aviso-privacidad/aceptacion",
        json={"acepta_aviso_privacidad": True, "version_aviso_privacidad": "2099-01-01"},
        headers=encabezados,
    )
    assert conflicto.status_code == 409
    assert conflicto.json()["detalle"]["codigo"] == "CONFLICTO_REVISION"
    monkeypatch.setattr(
        "app.core.privacidad.VERSION_AVISO_PRIVACIDAD_VIGENTE", "2027-01-01"
    )
    futura = cliente.get("/api/v1/autenticacion/usuario-actual", headers=encabezados)
    assert futura.status_code == 200
    assert futura.json()["aviso_privacidad"]["requiere_aceptar"] is True


def test_aceptacion_se_aísla_por_usuario_y_cascada_al_eliminar(
    cliente: TestClient, admin: Engine
) -> None:
    correo_a = _correo("aislamiento-a")
    correo_b = _correo("aislamiento-b")
    respuestas = []
    for correo in (correo_a, correo_b):
        respuesta = cliente.post(
            "/api/v1/autenticacion/registro",
            json={
                "nombre_completo": "Aislamiento QA",
                "correo": correo,
                "contrasena": "una-contrasena-larga-1",
                "acepta_aviso_privacidad": True,
                "version_aviso_privacidad": VERSION_AVISO_PRIVACIDAD_VIGENTE,
            },
        )
        assert respuesta.status_code == 201
        respuestas.append(respuesta.json())
    usuario_a = respuestas[0]["usuario"]["identificador"]
    usuario_b = respuestas[1]["usuario"]["identificador"]
    with admin.begin() as conexion:
        conexion.execute(
            text("DELETE FROM aceptacion_aviso_privacidad WHERE identificador_usuario=:usuario"),
            {"usuario": usuario_b},
        )
    token_b = respuestas[1]["token_acceso"]
    estado_b = cliente.get(
        "/api/v1/autenticacion/usuario-actual",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert estado_b.json()["aviso_privacidad"]["requiere_aceptar"] is True
    with admin.begin() as conexion:
        conexion.execute(
            text(
                "DELETE FROM membresia_usuario_en_organizacion WHERE identificador_usuario=:usuario"
            ),
            {"usuario": usuario_a},
        )
        conexion.execute(
            text("DELETE FROM usuario_plataforma WHERE identificador=:usuario"),
            {"usuario": usuario_a},
        )
    with admin.connect() as conexion:
        assert conexion.scalar(
            text("SELECT 1 FROM aceptacion_aviso_privacidad WHERE identificador_usuario=:usuario"),
            {"usuario": usuario_a},
        ) is None
