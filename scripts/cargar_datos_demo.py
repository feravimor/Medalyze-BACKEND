"""Carga las plantillas de demostración, nunca datos clínicos aprobados.

Uso local explícito:
    LOAD_DEMO_DATA=true python scripts/cargar_datos_demo.py
"""
from pathlib import Path

from sqlalchemy import create_engine

from app.core.config import obtener_configuracion


def cargar() -> None:
    configuracion = obtener_configuracion()
    if not configuracion.load_demo_data:
        raise RuntimeError("Activa LOAD_DEMO_DATA=true para cargar datos de demostración.")

    sql = (Path(__file__).parents[1] / "db" / "seed_demo.sql").read_text(encoding="utf-8")
    motor = create_engine(configuracion.database_url, pool_pre_ping=True)
    with motor.begin() as conexion:
        conexion.exec_driver_sql(sql.replace("%", "%%"))


if __name__ == "__main__":
    cargar()
    print("Datos de demostración cargados; no representan contenido clínico aprobado.")
