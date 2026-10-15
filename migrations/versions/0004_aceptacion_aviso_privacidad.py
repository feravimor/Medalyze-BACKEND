"""Agrega aceptación versionada del Aviso de Privacidad.

Revision ID: 0004
Revises: 0003
"""
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE aceptacion_aviso_privacidad (
          identificador_usuario uuid NOT NULL
            REFERENCES usuario_plataforma(identificador) ON DELETE CASCADE,
          version_aviso varchar(32) NOT NULL,
          aceptado_en timestamptz NOT NULL DEFAULT now(),
          PRIMARY KEY (identificador_usuario, version_aviso)
        )
    """)
    op.execute("ALTER TABLE aceptacion_aviso_privacidad ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE aceptacion_aviso_privacidad FORCE ROW LEVEL SECURITY")
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON aceptacion_aviso_privacidad TO medalyze_app"
    )
    op.execute("""
        CREATE POLICY aislamiento_aceptacion_aviso ON aceptacion_aviso_privacidad USING (
          EXISTS (
            SELECT 1 FROM membresia_usuario_en_organizacion m
            WHERE m.identificador_usuario = aceptacion_aviso_privacidad.identificador_usuario
              AND m.identificador_organizacion = organizacion_actual()
              AND m.activa
          )
        ) WITH CHECK (
          EXISTS (
            SELECT 1 FROM membresia_usuario_en_organizacion m
            WHERE m.identificador_usuario = aceptacion_aviso_privacidad.identificador_usuario
              AND m.identificador_organizacion = organizacion_actual()
              AND m.activa
          )
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE aceptacion_aviso_privacidad")
