"""Crea el esquema inicial de Medalyze.

Revision ID: 0001
Revises: None
"""

from pathlib import Path

from alembic import context, op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def _sql() -> str:
    contenido = (Path(__file__).parents[2] / "db" / "schema_0001.sql").read_text(encoding="utf-8")
    lineas = [
        linea for linea in contenido.splitlines() if linea.strip() not in {"BEGIN;", "COMMIT;"}
    ]
    return "\n".join(lineas)


def upgrade() -> None:
    sql = _sql()
    if context.is_offline_mode():
        op.execute(sql)
    else:
        op.get_bind().exec_driver_sql(sql.replace("%", "%%"))


def downgrade() -> None:
    raise RuntimeError(
        "El esquema inicial contiene datos financieros; el downgrade destructivo no está habilitado."
    )
