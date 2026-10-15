"""Permite limpiar demos con triggers activos y sin privilegios de superusuario.

Revision ID: 0009
Revises: 0008
"""

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


_TRIGGER_FUNCTION = """
CREATE OR REPLACE FUNCTION impedir_modificacion()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
  contexto uuid;
  organizacion uuid;
BEGIN
  IF TG_OP = 'DELETE' THEN
    BEGIN
      contexto := nullif(current_setting('app.demo_cleanup_organization', true), '')::uuid;
    EXCEPTION WHEN invalid_text_representation THEN
      contexto := NULL;
    END;

    IF contexto IS NOT NULL
       AND EXISTS (
         SELECT 1
         FROM sesion_demo_invitado
         WHERE identificador_organizacion = contexto
       )
    THEN
      IF TG_TABLE_NAME = 'version_configuracion_tratamiento' THEN
        SELECT t.identificador_organizacion
        INTO organizacion
        FROM tratamiento t
        WHERE t.identificador = OLD.identificador_tratamiento;
      ELSIF TG_TABLE_NAME = 'hoja_costos_tratamiento' THEN
        organizacion := OLD.identificador_organizacion;
      ELSIF TG_TABLE_NAME IN (
        'linea_insumo_hoja_costos',
        'aporte_a_costos_indirectos_hoja',
        'periodo_mensual_hoja_costos'
      ) THEN
        SELECT h.identificador_organizacion
        INTO organizacion
        FROM hoja_costos_tratamiento h
        WHERE h.identificador = OLD.identificador_hoja;
      ELSIF TG_TABLE_NAME = 'version_periodo_mensual_consumo' THEN
        SELECT p.identificador_organizacion
        INTO organizacion
        FROM periodo_mensual_consumo p
        WHERE p.identificador = OLD.identificador_periodo;
      END IF;

      IF organizacion = contexto THEN
        RETURN OLD;
      END IF;
    END IF;
  END IF;

  RAISE EXCEPTION 'La tabla % es inmutable', TG_TABLE_NAME;
END
$$;
"""

_PRICE_TRIGGER_FUNCTION = """
CREATE OR REPLACE FUNCTION impedir_modificacion_precio()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
  contexto uuid;
  organizacion uuid;
BEGIN
  IF TG_OP = 'DELETE' THEN
    BEGIN
      contexto := nullif(current_setting('app.demo_cleanup_organization', true), '')::uuid;
    EXCEPTION WHEN invalid_text_representation THEN
      contexto := NULL;
    END;

    IF contexto IS NOT NULL
       AND EXISTS (
         SELECT 1
         FROM sesion_demo_invitado
         WHERE identificador_organizacion = contexto
       )
    THEN
      IF TG_TABLE_NAME = 'precio_historico_insumo' THEN
        SELECT i.identificador_organizacion
        INTO organizacion
        FROM insumo_clinico i
        WHERE i.identificador = OLD.identificador_insumo;
      END IF;

      IF organizacion = contexto THEN
        RETURN OLD;
      END IF;
    END IF;
  END IF;

  RAISE EXCEPTION 'La tabla % es inmutable', TG_TABLE_NAME;
END
$$;
"""

_DELETE_FUNCTION = """
CREATE OR REPLACE FUNCTION eliminar_sesion_demo(p_organizacion uuid, p_usuario uuid)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  sesiones_registradas integer;
  usuario_registrado uuid;
BEGIN
  SELECT count(*)::integer
  INTO sesiones_registradas
  FROM sesion_demo_invitado
  WHERE identificador_organizacion = p_organizacion;

  IF sesiones_registradas <> 1 THEN
    RAISE EXCEPTION 'La organizacion no es una sesion demo propia';
  END IF;

  SELECT identificador_usuario
  INTO usuario_registrado
  FROM sesion_demo_invitado
  WHERE identificador_organizacion = p_organizacion
  FOR UPDATE;

  IF usuario_registrado IS DISTINCT FROM p_usuario THEN
    RAISE EXCEPTION 'La organizacion no es una sesion demo propia';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM membresia_usuario_en_organizacion
    WHERE identificador_usuario = p_usuario
      AND identificador_organizacion <> p_organizacion
  ) THEN
    RAISE EXCEPTION 'La cuenta demo tiene otra organizacion asociada';
  END IF;

  PERFORM set_config('app.demo_cleanup_organization', p_organizacion::text, true);

  -- Remove current-version references before deleting their target rows.
  UPDATE tratamiento
  SET identificador_version_vigente = NULL,
      identificador_hoja_vigente = NULL
  WHERE identificador_organizacion = p_organizacion;
  UPDATE periodo_mensual_consumo
  SET identificador_version_vigente = NULL
  WHERE identificador_organizacion = p_organizacion;
  UPDATE version_periodo_mensual_consumo v
  SET identificador_version_sustituida = NULL
  WHERE v.identificador_periodo IN (
    SELECT p.identificador
    FROM periodo_mensual_consumo p
    WHERE p.identificador_organizacion = p_organizacion
  );
  UPDATE hoja_costos_tratamiento h
  SET sustituye_a = NULL
  WHERE h.identificador_organizacion = p_organizacion;

  -- Delete immutable descendants while their organization is still registered.
  DELETE FROM linea_insumo_hoja_costos
  WHERE identificador_hoja IN (
    SELECT identificador
    FROM hoja_costos_tratamiento
    WHERE identificador_organizacion = p_organizacion
  );
  DELETE FROM aporte_a_costos_indirectos_hoja
  WHERE identificador_hoja IN (
    SELECT identificador
    FROM hoja_costos_tratamiento
    WHERE identificador_organizacion = p_organizacion
  );
  DELETE FROM periodo_mensual_hoja_costos
  WHERE identificador_hoja IN (
    SELECT identificador
    FROM hoja_costos_tratamiento
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
    SELECT identificador
    FROM tratamiento
    WHERE identificador_organizacion = p_organizacion
  );
  DELETE FROM version_configuracion_tratamiento
  WHERE identificador_tratamiento IN (
    SELECT identificador
    FROM tratamiento
    WHERE identificador_organizacion = p_organizacion
  );
  DELETE FROM tratamiento
  WHERE identificador_organizacion = p_organizacion;
  DELETE FROM version_periodo_mensual_consumo
  WHERE identificador_periodo IN (
    SELECT identificador
    FROM periodo_mensual_consumo
    WHERE identificador_organizacion = p_organizacion
  );
  DELETE FROM periodo_mensual_consumo
  WHERE identificador_organizacion = p_organizacion;
  DELETE FROM precio_historico_insumo
  WHERE identificador_insumo IN (
    SELECT identificador
    FROM insumo_clinico
    WHERE identificador_organizacion = p_organizacion
  );
  DELETE FROM insumo_clinico
  WHERE identificador_organizacion = p_organizacion;

  DELETE FROM gasto_registrado WHERE identificador_organizacion = p_organizacion;
  DELETE FROM equipo_o_instalacion_depreciable
  WHERE identificador_organizacion = p_organizacion;
  DELETE FROM perfil_capacidad_atencion
  WHERE identificador_organizacion = p_organizacion;
  DELETE FROM solicitud_idempotente WHERE identificador_organizacion = p_organizacion;
  DELETE FROM preferencias_onboarding_usuario
  WHERE identificador_organizacion = p_organizacion;
  DELETE FROM token_actualizacion_sesion
  WHERE identificador_organizacion = p_organizacion
     OR identificador_usuario = p_usuario;
  DELETE FROM aceptacion_aviso_privacidad WHERE identificador_usuario = p_usuario;
  DELETE FROM especialidad_seleccionada_por_usuario WHERE identificador_usuario = p_usuario;
  DELETE FROM membresia_usuario_en_organizacion
  WHERE identificador_organizacion = p_organizacion
    AND identificador_usuario = p_usuario;

  -- Keep the marker until all protected tables have been removed.
  DELETE FROM sesion_demo_invitado
  WHERE identificador_organizacion = p_organizacion
    AND identificador_usuario = p_usuario;
  DELETE FROM organizacion_consultorio WHERE identificador = p_organizacion;
  DELETE FROM usuario_plataforma WHERE identificador = p_usuario;
END
$$;
"""


def upgrade() -> None:
    op.execute(_TRIGGER_FUNCTION)
    op.execute(_PRICE_TRIGGER_FUNCTION)
    op.execute(_DELETE_FUNCTION)
    op.execute("REVOKE ALL ON FUNCTION eliminar_sesion_demo(uuid, uuid) FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION eliminar_sesion_demo(uuid, uuid) TO medalyze_app")


def downgrade() -> None:
    raise RuntimeError("La correccion de eliminacion demo no admite downgrade destructivo.")
