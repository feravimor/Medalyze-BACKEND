"""Carga datos de demostración para una organización existente.

Uso:
    python scripts/datos_sinteticos.py --organizacion <uuid>
"""
import argparse
from uuid import UUID

from sqlalchemy import create_engine, text

from app.core.config import obtener_configuracion


def cargar(organizacion: UUID) -> None:
    motor = create_engine(obtener_configuracion().database_url, pool_pre_ping=True)
    with motor.begin() as conexion:
        conexion.execute(
            text("SELECT set_config('app.organizacion_id', :organizacion, true)"),
            {"organizacion": str(organizacion)},
        )
        conexion.execute(
            text("""
                INSERT INTO perfil_capacidad_atencion
                  (identificador_organizacion, dias_por_semana, horas_por_dia, porcentaje_ocupacion)
                SELECT :organizacion, 5, 8, 75
                WHERE NOT EXISTS (
                  SELECT 1 FROM perfil_capacidad_atencion
                  WHERE identificador_organizacion=:organizacion AND fecha_fin_vigencia IS NULL
                )
            """),
            {"organizacion": organizacion},
        )
        conexion.execute(
            text("""
                INSERT INTO gasto_registrado
                  (identificador_organizacion, nombre, categoria,
                   importe_pagado_por_periodo, codigo_periodicidad, fecha_inicio_vigencia)
                SELECT :organizacion, datos.nombre, datos.categoria::categoria_gasto,
                       datos.importe, 'MENSUAL', current_date
                FROM (VALUES
                  ('Renta del consultorio', 'FIJO', 6000),
                  ('Servicios', 'VARIABLE', 1200)
                ) AS datos(nombre, categoria, importe)
                WHERE NOT EXISTS (
                  SELECT 1 FROM gasto_registrado gasto
                  WHERE gasto.identificador_organizacion=:organizacion
                    AND gasto.nombre=datos.nombre AND gasto.fecha_fin_vigencia IS NULL
                )
            """),
            {"organizacion": organizacion},
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--organizacion", required=True, type=UUID)
    argumentos = parser.parse_args()
    cargar(argumentos.organizacion)
    print("Datos sintéticos cargados correctamente.")


if __name__ == "__main__":
    main()
