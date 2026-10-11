"""Preparación común de las pruebas que usan PostgreSQL."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine

RAIZ = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session", autouse=True)
def plantillas_de_demostracion() -> None:
    """Carga las plantillas de demostración que varias pruebas necesitan.

    Las migraciones solo cargan catálogos técnicos; las plantillas son datos de demostración y no se
    cargan nunca en producción (``LOAD_DEMO_DATA``). Las pruebas las cargan aquí, de forma idempotente,
    para no depender de un paso manual ni de un paso especial del CI.
    """
    if os.getenv("MEDALYZE_TEST_POSTGRES") != "1":
        return
    from app.core.config import obtener_configuracion

    motor = create_engine(obtener_configuracion().database_url, pool_pre_ping=True)
    sql = (RAIZ / "db" / "seed_demo.sql").read_text(encoding="utf-8")
    with motor.begin() as conexion:
        conexion.exec_driver_sql(sql.replace("%", "%%"))
    motor.dispose()
