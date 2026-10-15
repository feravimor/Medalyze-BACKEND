"""Completa la eliminación demo sin eventos de triggers pendientes.

Revision ID: 0008
Revises: 0007
"""

from alembic import op

revision = "0008"
down_revision = "0007"
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

          SET LOCAL session_replication_role = replica;
          DELETE FROM linea_insumo_hoja_costos
          WHERE identificador_hoja IN (
            SELECT identificador FROM hoja_costos_tratamiento
            WHERE identificador_organizacion = p_organizacion
          );
          DELETE FROM aporte_a_costos_indirectos_hoja
          WHERE identificador_hoja IN (
            SELECT identificador FROM hoja_costos_tratamiento
            WHERE identificador_organizacion = p_organizacion
          );
          DELETE FROM periodo_mensual_hoja_costos
          WHERE identificador_hoja IN (
            SELECT identificador FROM hoja_costos_tratamiento
            WHERE identificador_organizacion = p_organizacion
          );
          DELETE FROM hoja_costos_tratamiento
          WHERE identificador_organizacion = p_organizacion;
          DELETE FROM linea_receta_insumos_tratamiento
          WHERE identificador_version_configuracion IN (
            SELECT v.identificador
            FROM version_configuracion_tratamiento v
            JOIN tratamiento t ON t.identificador = v.identificador_tratamiento
            WHERE t.identificador_organizacion = p_organizacion
          );
          DELETE FROM material_sugerido_tratamiento
          WHERE identificador_tratamiento IN (
            SELECT identificador FROM tratamiento
            WHERE identificador_organizacion = p_organizacion
          );
          DELETE FROM version_configuracion_tratamiento
          WHERE identificador_tratamiento IN (
            SELECT identificador FROM tratamiento
            WHERE identificador_organizacion = p_organizacion
          );
          DELETE FROM tratamiento WHERE identificador_organizacion = p_organizacion;
          DELETE FROM version_periodo_mensual_consumo
          WHERE identificador_periodo IN (
            SELECT identificador FROM periodo_mensual_consumo
            WHERE identificador_organizacion = p_organizacion
          );
          DELETE FROM periodo_mensual_consumo
          WHERE identificador_organizacion = p_organizacion;
          DELETE FROM precio_historico_insumo
          WHERE identificador_insumo IN (
            SELECT identificador FROM insumo_clinico
            WHERE identificador_organizacion = p_organizacion
          );
          DELETE FROM insumo_clinico WHERE identificador_organizacion = p_organizacion;
          DELETE FROM gasto_registrado WHERE identificador_organizacion = p_organizacion;
          DELETE FROM equipo_o_instalacion_depreciable WHERE identificador_organizacion = p_organizacion;
          DELETE FROM perfil_capacidad_atencion WHERE identificador_organizacion = p_organizacion;
          DELETE FROM solicitud_idempotente WHERE identificador_organizacion = p_organizacion;
          DELETE FROM preferencias_onboarding_usuario WHERE identificador_organizacion = p_organizacion;
          DELETE FROM sesion_demo_invitado WHERE identificador_organizacion = p_organizacion;
          DELETE FROM token_actualizacion_sesion
          WHERE identificador_organizacion = p_organizacion OR identificador_usuario = p_usuario;
          DELETE FROM aceptacion_aviso_privacidad WHERE identificador_usuario = p_usuario;
          DELETE FROM especialidad_seleccionada_por_usuario WHERE identificador_usuario = p_usuario;
          DELETE FROM membresia_usuario_en_organizacion
          WHERE identificador_organizacion = p_organizacion AND identificador_usuario = p_usuario;
          DELETE FROM organizacion_consultorio WHERE identificador = p_organizacion;
          DELETE FROM usuario_plataforma WHERE identificador = p_usuario;
        END;
        $$
        """
    )


def downgrade() -> None:
    raise RuntimeError("La corrección de eliminación demo no admite downgrade destructivo.")
