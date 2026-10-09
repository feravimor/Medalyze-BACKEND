"""El historial de precios solo puede borrarse por la cascada de eliminar un insumo.

Revision ID: 0003
Revises: 0002

Antes, el trigger solo bloqueaba UPDATE, y el rol de la aplicación podía ejecutar
``DELETE FROM precio_historico_insumo`` directamente, alterando el historial. El comentario del
esquema decía "solo por cascada" pero nada lo hacía cumplir. Un DELETE originado por la cascada
de una llave foránea corre a profundidad de trigger 2; uno directo, a profundidad 1.
"""
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE FUNCTION impedir_modificacion_precio() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF TG_OP = 'DELETE' AND pg_trigger_depth() > 1 THEN
            RETURN OLD;  -- cascada por eliminar un insumo sin uso
          END IF;
          RAISE EXCEPTION 'La tabla % es inmutable', TG_TABLE_NAME;
        END $$;
    """)
    op.execute("DROP TRIGGER precio_inmutable ON precio_historico_insumo")
    op.execute("""
        CREATE TRIGGER precio_inmutable BEFORE UPDATE OR DELETE ON precio_historico_insumo
        FOR EACH ROW EXECUTE FUNCTION impedir_modificacion_precio()
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER precio_inmutable ON precio_historico_insumo")
    op.execute("""
        CREATE TRIGGER precio_inmutable BEFORE UPDATE ON precio_historico_insumo
        FOR EACH ROW EXECUTE FUNCTION impedir_modificacion()
    """)
    op.execute("DROP FUNCTION impedir_modificacion_precio()")
