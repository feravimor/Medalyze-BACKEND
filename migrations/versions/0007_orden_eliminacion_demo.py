"""Corrige el orden de eliminación de recetas demo.

Revision ID: 0007
Revises: 0006
"""

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION eliminar_sesion_demo(p_organizacion uuid, p_usuario uuid)
        RETURNS void
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = public
        AS $$
        DECLARE usuario_registrado uuid;
        BEGIN
          SELECT identificador_usuario INTO usuario_registrado
          FROM sesion_demo_invitado
          WHERE identificador_organizacion = p_organizacion
          FOR UPDATE;
          IF usuario_registrado IS NULL OR usuario_registrado <> p_usuario THEN
            RAISE EXCEPTION 'La organización no es una sesión demo propia';
          END IF;
          IF EXISTS (
            SELECT 1 FROM membresia_usuario_en_organizacion
            WHERE identificador_usuario = p_usuario
              AND identificador_organizacion <> p_organizacion
          ) THEN
            RAISE EXCEPTION 'La cuenta demo tiene otra organización asociada';
          END IF;

          ALTER TABLE version_configuracion_tratamiento DISABLE TRIGGER USER;
          ALTER TABLE version_periodo_mensual_consumo DISABLE TRIGGER USER;
          ALTER TABLE hoja_costos_tratamiento DISABLE TRIGGER USER;
          ALTER TABLE linea_insumo_hoja_costos DISABLE TRIGGER USER;
          ALTER TABLE aporte_a_costos_indirectos_hoja DISABLE TRIGGER USER;
          ALTER TABLE periodo_mensual_hoja_costos DISABLE TRIGGER USER;
          DELETE FROM linea_receta_insumos_tratamiento
          WHERE identificador_version_configuracion IN (
            SELECT v.identificador
            FROM version_configuracion_tratamiento v
            JOIN tratamiento t ON t.identificador = v.identificador_tratamiento
            WHERE t.identificador_organizacion = p_organizacion
          );
          DELETE FROM membresia_usuario_en_organizacion
          WHERE identificador_organizacion = p_organizacion
            AND identificador_usuario = p_usuario;
          DELETE FROM organizacion_consultorio
          WHERE identificador = p_organizacion;
          ALTER TABLE version_configuracion_tratamiento ENABLE TRIGGER USER;
          ALTER TABLE version_periodo_mensual_consumo ENABLE TRIGGER USER;
          ALTER TABLE hoja_costos_tratamiento ENABLE TRIGGER USER;
          ALTER TABLE linea_insumo_hoja_costos ENABLE TRIGGER USER;
          ALTER TABLE aporte_a_costos_indirectos_hoja ENABLE TRIGGER USER;
          ALTER TABLE periodo_mensual_hoja_costos ENABLE TRIGGER USER;
          DELETE FROM usuario_plataforma WHERE identificador = p_usuario;
        END;
        $$
        """
    )


def downgrade() -> None:
    raise RuntimeError("La corrección de orden de eliminación no admite downgrade destructivo.")
