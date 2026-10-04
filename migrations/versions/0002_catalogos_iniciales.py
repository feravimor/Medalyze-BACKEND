"""Carga catálogos y plantillas iniciales.

Revision ID: 0002
Revises: 0001
"""
from pathlib import Path

from alembic import context, op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def _semillas() -> str:
    contenido = (Path(__file__).parents[2] / "db" / "seed.sql").read_text(encoding="utf-8")
    lineas = [linea for linea in contenido.splitlines() if linea.strip() not in {"BEGIN;", "COMMIT;"}]
    return "\n".join(lineas)


def upgrade() -> None:
    sql = _semillas()
    if context.is_offline_mode():
        op.execute(sql)
    else:
        op.get_bind().exec_driver_sql(sql.replace("%", "%%"))


def downgrade() -> None:
    raise RuntimeError("Los catálogos pueden estar referenciados; su eliminación automática no está habilitada.")
