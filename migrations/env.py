import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

url = os.getenv("ALEMBIC_DATABASE_URL") or os.getenv("DATABASE_URL")
if url:
    config.set_main_option("sqlalchemy.url", url)


def ejecutar_migraciones_sin_conexion() -> None:
    context.configure(url=config.get_main_option("sqlalchemy.url"), literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def ejecutar_migraciones_con_conexion() -> None:
    motor = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with motor.connect() as conexion:
        context.configure(connection=conexion)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    ejecutar_migraciones_sin_conexion()
else:
    ejecutar_migraciones_con_conexion()
