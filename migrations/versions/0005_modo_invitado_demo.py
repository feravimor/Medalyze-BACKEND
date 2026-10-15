"""Agrega metadatos de sesiones demo y la unidad centímetro.

Revision ID: 0005
Revises: 0004
"""

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE token_actualizacion_sesion ADD COLUMN es_invitado boolean NOT NULL DEFAULT false"
    )
    op.execute(
        "ALTER TABLE token_actualizacion_sesion ADD COLUMN fecha_hora_expiracion_invitado timestamptz"
    )
    op.execute("""
        CREATE TABLE sesion_demo_invitado (
          identificador_organizacion uuid PRIMARY KEY REFERENCES organizacion_consultorio(identificador) ON DELETE CASCADE,
          identificador_usuario uuid NOT NULL UNIQUE REFERENCES usuario_plataforma(identificador) ON DELETE CASCADE,
          clave_escenario varchar(80) NOT NULL,
          expira_en timestamptz NOT NULL,
          fecha_hora_creacion timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("ALTER TABLE sesion_demo_invitado ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE sesion_demo_invitado FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY aislamiento_sesion_demo ON sesion_demo_invitado
        USING (identificador_organizacion = organizacion_actual())
        WITH CHECK (identificador_organizacion = organizacion_actual())
    """)
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON sesion_demo_invitado TO medalyze_app")
    op.execute(
        "INSERT INTO unidad_medida_insumo (codigo, nombre, orden) VALUES ('CM', 'cm', 15) ON CONFLICT DO NOTHING"
    )


def downgrade() -> None:
    op.execute("DROP TABLE sesion_demo_invitado")
    op.execute("ALTER TABLE token_actualizacion_sesion DROP COLUMN fecha_hora_expiracion_invitado")
    op.execute("ALTER TABLE token_actualizacion_sesion DROP COLUMN es_invitado")
    op.execute("DELETE FROM unidad_medida_insumo WHERE codigo = 'CM'")
