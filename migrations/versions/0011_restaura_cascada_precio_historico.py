"""Restaura la cascada de borrado del historial de precios sin perder la limpieza demo.

Revision ID: 0011
Revises: 0010

La migración 0009 reescribió ``impedir_modificacion_precio()`` para permitir la limpieza de las
organizaciones demo, pero omitió la rama de la 0003: un DELETE originado por la cascada de eliminar un
insumo sin uso corre a profundidad de trigger 2 y debe permitirse. Sin ella, ``DELETE /insumos/{id}``
falla para cualquier insumo sin uso. Aquí se conservan las dos reglas.
"""

from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

_FUNCION = """
CREATE OR REPLACE FUNCTION impedir_modificacion_precio()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
  contexto uuid;
  organizacion uuid;
BEGIN
  IF TG_OP = 'DELETE' THEN
    -- Cascada por eliminar un insumo sin uso (0003): un DELETE directo corre a profundidad 1.
    IF pg_trigger_depth() > 1 THEN
      RETURN OLD;
    END IF;

    -- Limpieza de una organizacion demo registrada (0009).
    BEGIN
      contexto := nullif(current_setting('app.demo_cleanup_organization', true), '')::uuid;
    EXCEPTION WHEN invalid_text_representation THEN
      contexto := NULL;
    END;

    IF contexto IS NOT NULL
       AND EXISTS (
         SELECT 1 FROM sesion_demo_invitado WHERE identificador_organizacion = contexto
       )
    THEN
      SELECT i.identificador_organizacion
      INTO organizacion
      FROM insumo_clinico i
      WHERE i.identificador = OLD.identificador_insumo;

      IF organizacion = contexto THEN
        RETURN OLD;
      END IF;
    END IF;
  END IF;

  RAISE EXCEPTION 'La tabla % es inmutable', TG_TABLE_NAME;
END
$$;
"""


def upgrade() -> None:
    op.execute(_FUNCION)


def downgrade() -> None:
    raise RuntimeError("Esta correccion no admite downgrade: dejaria sin cascada el historial de precios.")
