from collections.abc import Iterator
from uuid import UUID

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import obtener_configuracion

configuracion = obtener_configuracion()
motor = create_engine(configuracion.database_url, pool_pre_ping=True)
fabrica_sesiones = sessionmaker(bind=motor, expire_on_commit=False, autoflush=False)


def obtener_sesion() -> Iterator[Session]:
    with fabrica_sesiones() as sesion:
        yield sesion


def fijar_contexto_organizacion(sesion: Session, identificador: UUID) -> None:
    """Debe ejecutarse dentro de la misma transacción que las consultas protegidas."""
    sesion.execute(
        text("SELECT set_config('app.organizacion_id', :valor, true)"),
        {"valor": str(identificador)},
    )


def comprobar_disponibilidad() -> bool:
    try:
        with motor.connect() as conexion:
            conexion.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
