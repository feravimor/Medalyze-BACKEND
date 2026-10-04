import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

pytestmark = pytest.mark.postgres


def _motores():
    if os.getenv("MEDALYZE_TEST_POSTGRES") != "1":
        pytest.skip("Las pruebas PostgreSQL se ejecutan en CI con MEDALYZE_TEST_POSTGRES=1.")
    return (
        create_engine(os.environ["ALEMBIC_DATABASE_URL"], pool_pre_ping=True),
        create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True),
    )


@pytest.fixture
def organizaciones():
    administrador, aplicacion = _motores()
    nombre_a = f"RLS A {uuid4()}"
    nombre_b = f"RLS B {uuid4()}"
    with administrador.begin() as conexion:
        organizacion_a = conexion.scalar(
            text("""
                INSERT INTO organizacion_consultorio (nombre_comercial)
                VALUES (:nombre) RETURNING identificador
            """),
            {"nombre": nombre_a},
        )
        organizacion_b = conexion.scalar(
            text("""
                INSERT INTO organizacion_consultorio (nombre_comercial)
                VALUES (:nombre) RETURNING identificador
            """),
            {"nombre": nombre_b},
        )
    try:
        yield administrador, aplicacion, organizacion_a, organizacion_b
    finally:
        with administrador.begin() as conexion:
            conexion.execute(
                text("DELETE FROM organizacion_consultorio WHERE identificador IN (:a,:b)"),
                {"a": organizacion_a, "b": organizacion_b},
            )
        administrador.dispose()
        aplicacion.dispose()


def _fijar_organizacion(conexion, organizacion) -> None:
    conexion.execute(
        text("SELECT set_config('app.organizacion_id', :organizacion, true)"),
        {"organizacion": str(organizacion)},
    )


def _insertar_gasto(conexion, organizacion, nombre: str) -> None:
    conexion.execute(
        text("""
            INSERT INTO gasto_registrado
              (identificador_organizacion,nombre,categoria,importe_pagado_por_periodo,
               codigo_periodicidad,fecha_inicio_vigencia)
            VALUES (:organizacion,:nombre,'FIJO',100,'MENSUAL',current_date)
        """),
        {"organizacion": organizacion, "nombre": nombre},
    )


def test_rls_aisla_dos_organizaciones(organizaciones) -> None:
    _, aplicacion, organizacion_a, organizacion_b = organizaciones
    nombre_a = f"Gasto A {uuid4()}"
    nombre_b = f"Gasto B {uuid4()}"
    with aplicacion.begin() as conexion:
        _fijar_organizacion(conexion, organizacion_a)
        _insertar_gasto(conexion, organizacion_a, nombre_a)
    with aplicacion.begin() as conexion:
        _fijar_organizacion(conexion, organizacion_b)
        _insertar_gasto(conexion, organizacion_b, nombre_b)
    with aplicacion.begin() as conexion:
        _fijar_organizacion(conexion, organizacion_a)
        visibles = conexion.execute(
            text("SELECT identificador_organizacion,nombre FROM gasto_registrado")
        ).mappings().all()
    assert any(fila["nombre"] == nombre_a for fila in visibles)
    assert all(fila["identificador_organizacion"] == organizacion_a for fila in visibles)
    assert all(fila["nombre"] != nombre_b for fila in visibles)


def test_transaccion_revierte_escritura_parcial(organizaciones) -> None:
    _, aplicacion, organizacion_a, _ = organizaciones
    nombre = f"Debe revertirse {uuid4()}"
    with pytest.raises(IntegrityError), aplicacion.begin() as conexion:
        _fijar_organizacion(conexion, organizacion_a)
        _insertar_gasto(conexion, organizacion_a, nombre)
        conexion.execute(
            text("""
                    INSERT INTO equipo_o_instalacion_depreciable
                      (identificador_organizacion,nombre,precio_adquisicion,vida_util_anios)
                    VALUES (:organizacion,'Inválido',1000,0)
                """),
            {"organizacion": organizacion_a},
        )
    with aplicacion.begin() as conexion:
        _fijar_organizacion(conexion, organizacion_a)
        cantidad = conexion.scalar(
            text("SELECT count(*) FROM gasto_registrado WHERE nombre=:nombre"),
            {"nombre": nombre},
        )
    assert cantidad == 0


def test_rol_aplicacion_no_es_superusuario_y_rls_esta_activo(organizaciones) -> None:
    _, aplicacion, _, _ = organizaciones
    with aplicacion.connect() as conexion:
        usuario = conexion.scalar(text("SELECT current_user"))
        superusuario = conexion.scalar(
            text("SELECT rolsuper FROM pg_roles WHERE rolname=current_user")
        )
        rls_activo = conexion.scalar(
            text("SELECT relrowsecurity FROM pg_class WHERE relname='gasto_registrado'")
        )
    assert usuario == "medalyze_app"
    assert superusuario is False
    assert rls_activo is True
