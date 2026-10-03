BEGIN;

-- Rol local de ejecución. El propietario aplica el esquema; la API usa este rol
-- sin privilegios administrativos para que PostgreSQL haga cumplir RLS.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'medalyze_app') THEN
    CREATE ROLE medalyze_app LOGIN PASSWORD 'medalyze_app'
      NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
  END IF;
END $$;

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS citext;

CREATE TYPE rol_usuario_en_organizacion AS ENUM ('PROPIETARIO', 'COLABORADOR');
CREATE TYPE ruta_onboarding AS ENUM ('ASISTENTE_GUIADO', 'CAPTURA_DIRECTA_DATOS');
CREATE TYPE situacion_consultorio AS ENUM ('YA_ATIENDE_EN_CONSULTA_PRIVADA', 'ESTA_POR_INICIAR');
CREATE TYPE categoria_gasto AS ENUM ('FIJO', 'VARIABLE');
CREATE TYPE estado_equipo AS ENUM ('ACTIVO', 'ARCHIVADO', 'BAJA');
CREATE TYPE tipo_movimiento_periodo_mensual AS ENUM ('CAPTURA_INICIAL', 'CORRECCION', 'ANULACION', 'RESTAURACION');
CREATE TYPE procedencia_periodo_mensual AS ENUM ('ESTE_MES', 'PERIODO_ANTERIOR');
CREATE TYPE estado_tratamiento AS ENUM ('BORRADOR', 'CALCULADO', 'CAMBIOS_POR_REVISAR', 'ARCHIVADO');
CREATE TYPE metodo_materiales AS ENUM ('PROMEDIO_MENSUAL', 'IMPORTE_RAPIDO', 'RECETA_INSUMOS');
CREATE TYPE tipo_linea_receta AS ENUM ('RECETA_GENERAL', 'INSUMO_ESPECIAL');
CREATE TYPE tipo_origen_aporte AS ENUM ('GASTO', 'EQUIPO');
CREATE TYPE semaforo_margen AS ENUM ('BAJO', 'INTERMEDIO', 'ALTO');
CREATE TYPE madurez_base AS ENUM ('SIN_BASE', 'INICIAL', 'EN_FORMACION', 'MADURA');
CREATE TYPE motivo_exclusion_promedio AS ENUM ('ANULADO', 'FUTURO', 'SIN_TRATAMIENTOS', 'FUERA_DE_VENTANA');

CREATE FUNCTION actualizar_fecha_modificacion() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN NEW.fecha_hora_ultima_actualizacion = now(); RETURN NEW; END $$;

CREATE FUNCTION impedir_modificacion() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'La tabla % es inmutable', TG_TABLE_NAME; END $$;

CREATE FUNCTION organizacion_actual() RETURNS uuid LANGUAGE sql STABLE AS $$
  SELECT nullif(current_setting('app.organizacion_id', true), '')::uuid
$$;

CREATE TABLE usuario_plataforma (
  identificador uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  correo citext NOT NULL UNIQUE,
  hash_contrasena text NOT NULL,
  nombre_completo varchar(160) NOT NULL,
  fecha_hora_ultimo_inicio_sesion timestamptz,
  revision integer NOT NULL DEFAULT 0 CHECK (revision >= 0),
  fecha_hora_creacion timestamptz NOT NULL DEFAULT now(),
  fecha_hora_ultima_actualizacion timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE organizacion_consultorio (
  identificador uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  nombre_comercial varchar(160) NOT NULL,
  codigo_moneda char(3) NOT NULL DEFAULT 'MXN',
  multiplo_redondeo numeric(10,2) NOT NULL DEFAULT 50 CHECK (multiplo_redondeo > 0),
  espaciado_por_defecto smallint CHECK (espaciado_por_defecto BETWEEN 0 AND 15),
  revision integer NOT NULL DEFAULT 0 CHECK (revision >= 0),
  fecha_hora_creacion timestamptz NOT NULL DEFAULT now(),
  fecha_hora_ultima_actualizacion timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE membresia_usuario_en_organizacion (
  identificador uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  identificador_usuario uuid NOT NULL REFERENCES usuario_plataforma(identificador),
  identificador_organizacion uuid NOT NULL REFERENCES organizacion_consultorio(identificador),
  rol rol_usuario_en_organizacion NOT NULL DEFAULT 'PROPIETARIO',
  activa boolean NOT NULL DEFAULT true,
  fecha_hora_creacion timestamptz NOT NULL DEFAULT now(),
  UNIQUE (identificador_usuario, identificador_organizacion)
);

CREATE TABLE token_actualizacion_sesion (
  identificador uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  identificador_usuario uuid NOT NULL REFERENCES usuario_plataforma(identificador) ON DELETE CASCADE,
  identificador_organizacion uuid NOT NULL REFERENCES organizacion_consultorio(identificador) ON DELETE CASCADE,
  hash_token text NOT NULL UNIQUE,
  fecha_hora_expiracion timestamptz NOT NULL,
  fecha_hora_revocacion timestamptz,
  reemplazado_por uuid REFERENCES token_actualizacion_sesion(identificador),
  descripcion_dispositivo text,
  fecha_hora_creacion timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE especialidad_odontologica (
  identificador uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  clave varchar(60) NOT NULL UNIQUE,
  nombre varchar(120) NOT NULL,
  orden smallint NOT NULL
);

CREATE TABLE especialidad_seleccionada_por_usuario (
  identificador_usuario uuid NOT NULL REFERENCES usuario_plataforma(identificador) ON DELETE CASCADE,
  identificador_especialidad uuid NOT NULL REFERENCES especialidad_odontologica(identificador),
  fecha_hora_creacion timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (identificador_usuario, identificador_especialidad)
);

CREATE TABLE preferencias_onboarding_usuario (
  identificador uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  identificador_usuario uuid NOT NULL UNIQUE REFERENCES usuario_plataforma(identificador) ON DELETE CASCADE,
  identificador_organizacion uuid NOT NULL REFERENCES organizacion_consultorio(identificador) ON DELETE CASCADE,
  ruta ruta_onboarding,
  situacion situacion_consultorio,
  ultimo_paso varchar(80),
  seleccion_parcial jsonb NOT NULL DEFAULT '{}'::jsonb,
  completado boolean NOT NULL DEFAULT false,
  revision integer NOT NULL DEFAULT 0,
  fecha_hora_creacion timestamptz NOT NULL DEFAULT now(),
  fecha_hora_ultima_actualizacion timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE perfil_capacidad_atencion (
  identificador uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  identificador_organizacion uuid NOT NULL REFERENCES organizacion_consultorio(identificador) ON DELETE CASCADE,
  dias_por_semana smallint NOT NULL CHECK (dias_por_semana BETWEEN 1 AND 7),
  horas_por_dia numeric(4,2) NOT NULL CHECK (horas_por_dia > 0 AND horas_por_dia <= 24),
  porcentaje_ocupacion numeric(5,2) NOT NULL DEFAULT 70 CHECK (porcentaje_ocupacion BETWEEN 0 AND 100),
  ocupacion_confirmada boolean NOT NULL DEFAULT false,
  fecha_inicio_vigencia date NOT NULL DEFAULT current_date,
  fecha_fin_vigencia date,
  revision integer NOT NULL DEFAULT 0,
  fecha_hora_creacion timestamptz NOT NULL DEFAULT now(),
  fecha_hora_ultima_actualizacion timestamptz NOT NULL DEFAULT now(),
  CHECK (fecha_fin_vigencia IS NULL OR fecha_fin_vigencia >= fecha_inicio_vigencia)
);
CREATE UNIQUE INDEX un_solo_perfil_capacidad_vigente
  ON perfil_capacidad_atencion (identificador_organizacion) WHERE fecha_fin_vigencia IS NULL;

CREATE TABLE periodicidad_pago (
  codigo varchar(20) PRIMARY KEY,
  nombre varchar(40) NOT NULL,
  factor_mensual numeric(12,8) NOT NULL CHECK (factor_mensual > 0),
  orden smallint NOT NULL
);

CREATE TABLE gasto_registrado (
  identificador uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  identificador_organizacion uuid NOT NULL REFERENCES organizacion_consultorio(identificador) ON DELETE CASCADE,
  nombre varchar(160) NOT NULL,
  categoria categoria_gasto NOT NULL,
  importe_pagado_por_periodo numeric(14,2) NOT NULL CHECK (importe_pagado_por_periodo >= 0),
  codigo_periodicidad varchar(20) NOT NULL DEFAULT 'MENSUAL' REFERENCES periodicidad_pago(codigo),
  fecha_inicio_vigencia date NOT NULL,
  fecha_fin_vigencia date,
  activo boolean NOT NULL DEFAULT true,
  revision integer NOT NULL DEFAULT 0,
  fecha_hora_creacion timestamptz NOT NULL DEFAULT now(),
  fecha_hora_ultima_actualizacion timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE equipo_o_instalacion_depreciable (
  identificador uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  identificador_organizacion uuid NOT NULL REFERENCES organizacion_consultorio(identificador) ON DELETE CASCADE,
  nombre varchar(160) NOT NULL,
  precio_adquisicion numeric(14,2) NOT NULL CHECK (precio_adquisicion > 0),
  valor_residual numeric(14,2) NOT NULL DEFAULT 0 CHECK (valor_residual >= 0 AND valor_residual < precio_adquisicion),
  vida_util_anios smallint NOT NULL CHECK (vida_util_anios > 0),
  fecha_alta_en_servicio date,
  estado estado_equipo NOT NULL DEFAULT 'ACTIVO',
  depreciacion_mensual numeric(18,6) GENERATED ALWAYS AS ((precio_adquisicion - valor_residual) / (vida_util_anios * 12)) STORED,
  revision integer NOT NULL DEFAULT 0,
  fecha_hora_creacion timestamptz NOT NULL DEFAULT now(),
  fecha_hora_ultima_actualizacion timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE unidad_medida_insumo (
  codigo varchar(20) PRIMARY KEY,
  nombre varchar(40) NOT NULL,
  orden smallint NOT NULL
);

CREATE TABLE insumo_clinico (
  identificador uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  identificador_organizacion uuid NOT NULL REFERENCES organizacion_consultorio(identificador) ON DELETE CASCADE,
  nombre varchar(160) NOT NULL,
  nombre_normalizado varchar(160) GENERATED ALWAYS AS (lower(trim(nombre))) STORED,
  presentacion varchar(60),
  codigo_unidad varchar(20) NOT NULL REFERENCES unidad_medida_insumo(codigo),
  cantidad_contenida numeric(14,4) NOT NULL CHECK (cantidad_contenida > 0),
  fecha_hora_archivado timestamptz,
  revision integer NOT NULL DEFAULT 0,
  fecha_hora_creacion timestamptz NOT NULL DEFAULT now(),
  fecha_hora_ultima_actualizacion timestamptz NOT NULL DEFAULT now(),
  UNIQUE (identificador_organizacion, nombre_normalizado)
);

CREATE TABLE precio_historico_insumo (
  identificador uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  identificador_insumo uuid NOT NULL REFERENCES insumo_clinico(identificador) ON DELETE CASCADE,
  precio_presentacion numeric(14,2) NOT NULL CHECK (precio_presentacion >= 0),
  cantidad_contenida numeric(14,4) NOT NULL CHECK (cantidad_contenida > 0),
  costo_unitario numeric(18,6) GENERATED ALWAYS AS (precio_presentacion / cantidad_contenida) STORED,
  fecha_inicio_vigencia date NOT NULL DEFAULT current_date,
  fecha_hora_creacion timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE periodo_mensual_consumo (
  identificador uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  identificador_organizacion uuid NOT NULL REFERENCES organizacion_consultorio(identificador) ON DELETE CASCADE,
  mes date NOT NULL CHECK (extract(day FROM mes) = 1),
  identificador_version_vigente uuid,
  revision integer NOT NULL DEFAULT 0,
  fecha_hora_creacion timestamptz NOT NULL DEFAULT now(),
  fecha_hora_ultima_actualizacion timestamptz NOT NULL DEFAULT now(),
  UNIQUE (identificador_organizacion, mes)
);

CREATE TABLE version_periodo_mensual_consumo (
  identificador uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  identificador_periodo uuid NOT NULL REFERENCES periodo_mensual_consumo(identificador) ON DELETE CASCADE,
  numero_version smallint NOT NULL CHECK (numero_version > 0),
  tipo_movimiento tipo_movimiento_periodo_mensual NOT NULL,
  identificador_version_sustituida uuid REFERENCES version_periodo_mensual_consumo(identificador),
  consumo_materiales numeric(14,2) CHECK (consumo_materiales >= 0),
  tratamientos_atendidos integer CHECK (tratamientos_atendidos >= 0),
  procedencia procedencia_periodo_mensual,
  notas text,
  fecha_hora_creacion timestamptz NOT NULL DEFAULT now(),
  UNIQUE (identificador_periodo, numero_version)
);
ALTER TABLE periodo_mensual_consumo ADD CONSTRAINT fk_version_vigente
  FOREIGN KEY (identificador_version_vigente) REFERENCES version_periodo_mensual_consumo(identificador)
  DEFERRABLE INITIALLY DEFERRED;

CREATE TABLE plantilla_tratamiento (
  identificador uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  clave varchar(100) NOT NULL,
  version_catalogo varchar(30) NOT NULL,
  nombre varchar(160) NOT NULL,
  clave_especialidad varchar(60) NOT NULL,
  duracion_clinica smallint NOT NULL CHECK (duracion_clinica BETWEEN 1 AND 600),
  espaciado smallint CHECK (espaciado BETWEEN 0 AND 15),
  activa boolean NOT NULL DEFAULT true,
  UNIQUE (clave, version_catalogo)
);

CREATE TABLE material_sugerido_plantilla (
  identificador uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  identificador_plantilla uuid NOT NULL REFERENCES plantilla_tratamiento(identificador) ON DELETE CASCADE,
  nombre_generico varchar(160) NOT NULL,
  orden smallint NOT NULL,
  UNIQUE (identificador_plantilla, nombre_generico)
);

CREATE TABLE tratamiento (
  identificador uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  identificador_organizacion uuid NOT NULL REFERENCES organizacion_consultorio(identificador) ON DELETE CASCADE,
  nombre varchar(160) NOT NULL,
  especialidad varchar(100) NOT NULL,
  estado estado_tratamiento NOT NULL DEFAULT 'BORRADOR',
  identificador_version_vigente uuid,
  identificador_hoja_vigente uuid,
  fecha_hora_archivado timestamptz,
  revision integer NOT NULL DEFAULT 0,
  fecha_hora_creacion timestamptz NOT NULL DEFAULT now(),
  fecha_hora_ultima_actualizacion timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE version_configuracion_tratamiento (
  identificador uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  identificador_tratamiento uuid NOT NULL REFERENCES tratamiento(identificador) ON DELETE CASCADE,
  numero_version smallint NOT NULL CHECK (numero_version > 0),
  nombre varchar(160) NOT NULL,
  especialidad varchar(100) NOT NULL,
  duracion_clinica smallint NOT NULL CHECK (duracion_clinica BETWEEN 1 AND 600),
  espaciado smallint CHECK (espaciado BETWEEN 0 AND 15),
  metodo metodo_materiales,
  importe_materiales numeric(14,2) CHECK (importe_materiales >= 0),
  ajuste_porcentaje numeric(7,2) NOT NULL DEFAULT 1 CHECK (ajuste_porcentaje BETWEEN 1 AND 500),
  fecha_hora_creacion timestamptz NOT NULL DEFAULT now(),
  UNIQUE (identificador_tratamiento, numero_version)
);
ALTER TABLE tratamiento ADD CONSTRAINT fk_configuracion_vigente
  FOREIGN KEY (identificador_version_vigente) REFERENCES version_configuracion_tratamiento(identificador)
  DEFERRABLE INITIALLY DEFERRED;

CREATE TABLE linea_receta_insumos_tratamiento (
  identificador uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  identificador_version_configuracion uuid NOT NULL REFERENCES version_configuracion_tratamiento(identificador) ON DELETE CASCADE,
  identificador_insumo uuid NOT NULL REFERENCES insumo_clinico(identificador),
  tipo tipo_linea_receta NOT NULL DEFAULT 'RECETA_GENERAL',
  cantidad numeric(14,4) NOT NULL CHECK (cantidad > 0),
  merma_porcentaje numeric(5,2) NOT NULL DEFAULT 0 CHECK (merma_porcentaje BETWEEN 0 AND 100)
);

CREATE TABLE material_sugerido_tratamiento (
  identificador uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  identificador_tratamiento uuid NOT NULL REFERENCES tratamiento(identificador) ON DELETE CASCADE,
  nombre_generico varchar(160) NOT NULL,
  identificador_insumo uuid REFERENCES insumo_clinico(identificador),
  cantidad numeric(14,4) CHECK (cantidad > 0),
  UNIQUE (identificador_tratamiento, nombre_generico)
);

CREATE TABLE hoja_costos_tratamiento (
  identificador uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  identificador_organizacion uuid NOT NULL REFERENCES organizacion_consultorio(identificador) ON DELETE CASCADE,
  identificador_tratamiento uuid NOT NULL REFERENCES tratamiento(identificador),
  identificador_version_configuracion uuid NOT NULL REFERENCES version_configuracion_tratamiento(identificador),
  sustituye_a uuid REFERENCES hoja_costos_tratamiento(identificador),
  gastos_fijos numeric(24,10) NOT NULL,
  gastos_variables numeric(24,10) NOT NULL,
  depreciacion numeric(24,10) NOT NULL,
  pool_mensual numeric(24,10) NOT NULL,
  minutos_disponibles integer NOT NULL,
  minutos_efectivos integer NOT NULL,
  costo_por_minuto numeric(24,10) NOT NULL,
  minutos_imputados integer NOT NULL,
  costo_tiempo numeric(24,10) NOT NULL,
  materiales_generales numeric(24,10) NOT NULL,
  materiales_especiales numeric(24,10) NOT NULL,
  costo_total numeric(24,10) NOT NULL,
  ajuste_porcentaje numeric(7,2) NOT NULL,
  importe_ajustado numeric(24,10) NOT NULL,
  precio_sugerido numeric(24,10) NOT NULL,
  margen_porcentaje numeric(9,4) NOT NULL,
  semaforo semaforo_margen NOT NULL,
  madurez madurez_base NOT NULL DEFAULT 'SIN_BASE',
  version_formula varchar(30) NOT NULL DEFAULT '1.0.0',
  fecha_hora_creacion timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE tratamiento ADD CONSTRAINT fk_hoja_vigente
  FOREIGN KEY (identificador_hoja_vigente) REFERENCES hoja_costos_tratamiento(identificador)
  DEFERRABLE INITIALLY DEFERRED;

CREATE TABLE linea_insumo_hoja_costos (
  identificador uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  identificador_hoja uuid NOT NULL REFERENCES hoja_costos_tratamiento(identificador) ON DELETE CASCADE,
  identificador_insumo uuid REFERENCES insumo_clinico(identificador) ON DELETE SET NULL,
  nombre_insumo varchar(160) NOT NULL,
  cantidad numeric(14,4) NOT NULL,
  costo_unitario numeric(24,10) NOT NULL,
  subtotal numeric(24,10) NOT NULL
);

CREATE TABLE aporte_a_costos_indirectos_hoja (
  identificador uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  identificador_hoja uuid NOT NULL REFERENCES hoja_costos_tratamiento(identificador) ON DELETE CASCADE,
  tipo_origen tipo_origen_aporte NOT NULL,
  identificador_origen uuid,
  nombre varchar(160) NOT NULL,
  importe_original numeric(24,10) NOT NULL,
  equivalente_mensual numeric(24,10) NOT NULL,
  incluido boolean NOT NULL,
  motivo_exclusion varchar(100)
);

CREATE TABLE periodo_mensual_hoja_costos (
  identificador uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  identificador_hoja uuid NOT NULL REFERENCES hoja_costos_tratamiento(identificador) ON DELETE CASCADE,
  identificador_periodo uuid REFERENCES periodo_mensual_consumo(identificador) ON DELETE SET NULL,
  mes date NOT NULL,
  consumo_materiales numeric(24,10),
  tratamientos_atendidos integer,
  incluido boolean NOT NULL,
  motivo_exclusion motivo_exclusion_promedio
);

CREATE TABLE solicitud_idempotente (
  identificador uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  identificador_organizacion uuid NOT NULL REFERENCES organizacion_consultorio(identificador) ON DELETE CASCADE,
  identificador_usuario uuid NOT NULL REFERENCES usuario_plataforma(identificador) ON DELETE CASCADE,
  operacion varchar(100) NOT NULL,
  clave varchar(128) NOT NULL,
  hash_cuerpo text NOT NULL,
  estado_http smallint,
  respuesta jsonb,
  fecha_hora_expiracion timestamptz NOT NULL DEFAULT (now() + interval '24 hours'),
  fecha_hora_creacion timestamptz NOT NULL DEFAULT now(),
  UNIQUE (identificador_organizacion, identificador_usuario, operacion, clave)
);

CREATE TRIGGER usuario_actualizado BEFORE UPDATE ON usuario_plataforma FOR EACH ROW EXECUTE FUNCTION actualizar_fecha_modificacion();
CREATE TRIGGER organizacion_actualizada BEFORE UPDATE ON organizacion_consultorio FOR EACH ROW EXECUTE FUNCTION actualizar_fecha_modificacion();
CREATE TRIGGER onboarding_actualizado BEFORE UPDATE ON preferencias_onboarding_usuario FOR EACH ROW EXECUTE FUNCTION actualizar_fecha_modificacion();
CREATE TRIGGER capacidad_actualizada BEFORE UPDATE ON perfil_capacidad_atencion FOR EACH ROW EXECUTE FUNCTION actualizar_fecha_modificacion();
CREATE TRIGGER gasto_actualizado BEFORE UPDATE ON gasto_registrado FOR EACH ROW EXECUTE FUNCTION actualizar_fecha_modificacion();
CREATE TRIGGER equipo_actualizado BEFORE UPDATE ON equipo_o_instalacion_depreciable FOR EACH ROW EXECUTE FUNCTION actualizar_fecha_modificacion();
CREATE TRIGGER insumo_actualizado BEFORE UPDATE ON insumo_clinico FOR EACH ROW EXECUTE FUNCTION actualizar_fecha_modificacion();
CREATE TRIGGER periodo_actualizado BEFORE UPDATE ON periodo_mensual_consumo FOR EACH ROW EXECUTE FUNCTION actualizar_fecha_modificacion();
CREATE TRIGGER tratamiento_actualizado BEFORE UPDATE ON tratamiento FOR EACH ROW EXECUTE FUNCTION actualizar_fecha_modificacion();

-- El precio no se modifica. Se permite su borrado únicamente por la cascada que
-- acompaña la eliminación válida de un insumo sin uso clínico.
CREATE TRIGGER precio_inmutable BEFORE UPDATE ON precio_historico_insumo FOR EACH ROW EXECUTE FUNCTION impedir_modificacion();
CREATE TRIGGER version_mensual_inmutable BEFORE UPDATE OR DELETE ON version_periodo_mensual_consumo FOR EACH ROW EXECUTE FUNCTION impedir_modificacion();
CREATE TRIGGER configuracion_inmutable BEFORE UPDATE OR DELETE ON version_configuracion_tratamiento FOR EACH ROW EXECUTE FUNCTION impedir_modificacion();
CREATE TRIGGER hoja_inmutable BEFORE UPDATE OR DELETE ON hoja_costos_tratamiento FOR EACH ROW EXECUTE FUNCTION impedir_modificacion();
CREATE TRIGGER linea_hoja_inmutable BEFORE UPDATE OR DELETE ON linea_insumo_hoja_costos FOR EACH ROW EXECUTE FUNCTION impedir_modificacion();
CREATE TRIGGER aporte_hoja_inmutable BEFORE UPDATE OR DELETE ON aporte_a_costos_indirectos_hoja FOR EACH ROW EXECUTE FUNCTION impedir_modificacion();
CREATE TRIGGER periodo_hoja_inmutable BEFORE UPDATE OR DELETE ON periodo_mensual_hoja_costos FOR EACH ROW EXECUTE FUNCTION impedir_modificacion();

DO $$
DECLARE tabla text;
BEGIN
  FOREACH tabla IN ARRAY ARRAY[
    'perfil_capacidad_atencion','gasto_registrado','equipo_o_instalacion_depreciable',
    'insumo_clinico','periodo_mensual_consumo','tratamiento','hoja_costos_tratamiento',
    'preferencias_onboarding_usuario','solicitud_idempotente'
  ] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', tabla);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', tabla);
    EXECUTE format(
      'CREATE POLICY aislamiento_organizacion ON %I USING (identificador_organizacion = organizacion_actual()) WITH CHECK (identificador_organizacion = organizacion_actual())',
      tabla
    );
  END LOOP;
END $$;

ALTER TABLE precio_historico_insumo ENABLE ROW LEVEL SECURITY;
ALTER TABLE precio_historico_insumo FORCE ROW LEVEL SECURITY;
CREATE POLICY aislamiento_precio_insumo ON precio_historico_insumo USING (
  EXISTS (SELECT 1 FROM insumo_clinico i WHERE i.identificador = identificador_insumo AND i.identificador_organizacion = organizacion_actual())
);
ALTER TABLE version_periodo_mensual_consumo ENABLE ROW LEVEL SECURITY;
ALTER TABLE version_periodo_mensual_consumo FORCE ROW LEVEL SECURITY;
CREATE POLICY aislamiento_version_periodo ON version_periodo_mensual_consumo USING (
  EXISTS (SELECT 1 FROM periodo_mensual_consumo p WHERE p.identificador = identificador_periodo AND p.identificador_organizacion = organizacion_actual())
);
ALTER TABLE version_configuracion_tratamiento ENABLE ROW LEVEL SECURITY;
ALTER TABLE version_configuracion_tratamiento FORCE ROW LEVEL SECURITY;
CREATE POLICY aislamiento_version_tratamiento ON version_configuracion_tratamiento USING (
  EXISTS (SELECT 1 FROM tratamiento t WHERE t.identificador = identificador_tratamiento AND t.identificador_organizacion = organizacion_actual())
);

ALTER TABLE linea_receta_insumos_tratamiento ENABLE ROW LEVEL SECURITY;
ALTER TABLE linea_receta_insumos_tratamiento FORCE ROW LEVEL SECURITY;
CREATE POLICY aislamiento_linea_receta ON linea_receta_insumos_tratamiento USING (
  EXISTS (
    SELECT 1 FROM version_configuracion_tratamiento v
    JOIN tratamiento t ON t.identificador=v.identificador_tratamiento
    WHERE v.identificador=identificador_version_configuracion AND t.identificador_organizacion=organizacion_actual()
  )
);
ALTER TABLE material_sugerido_tratamiento ENABLE ROW LEVEL SECURITY;
ALTER TABLE material_sugerido_tratamiento FORCE ROW LEVEL SECURITY;
CREATE POLICY aislamiento_material_sugerido ON material_sugerido_tratamiento USING (
  EXISTS (SELECT 1 FROM tratamiento t WHERE t.identificador=identificador_tratamiento AND t.identificador_organizacion=organizacion_actual())
);
ALTER TABLE linea_insumo_hoja_costos ENABLE ROW LEVEL SECURITY;
ALTER TABLE linea_insumo_hoja_costos FORCE ROW LEVEL SECURITY;
CREATE POLICY aislamiento_linea_hoja ON linea_insumo_hoja_costos USING (
  EXISTS (SELECT 1 FROM hoja_costos_tratamiento h WHERE h.identificador=identificador_hoja AND h.identificador_organizacion=organizacion_actual())
);
ALTER TABLE aporte_a_costos_indirectos_hoja ENABLE ROW LEVEL SECURITY;
ALTER TABLE aporte_a_costos_indirectos_hoja FORCE ROW LEVEL SECURITY;
CREATE POLICY aislamiento_aporte_hoja ON aporte_a_costos_indirectos_hoja USING (
  EXISTS (SELECT 1 FROM hoja_costos_tratamiento h WHERE h.identificador=identificador_hoja AND h.identificador_organizacion=organizacion_actual())
);
ALTER TABLE periodo_mensual_hoja_costos ENABLE ROW LEVEL SECURITY;
ALTER TABLE periodo_mensual_hoja_costos FORCE ROW LEVEL SECURITY;
CREATE POLICY aislamiento_periodo_hoja ON periodo_mensual_hoja_costos USING (
  EXISTS (SELECT 1 FROM hoja_costos_tratamiento h WHERE h.identificador=identificador_hoja AND h.identificador_organizacion=organizacion_actual())
);

GRANT USAGE ON SCHEMA public TO medalyze_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO medalyze_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO medalyze_app;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO medalyze_app;

COMMIT;
