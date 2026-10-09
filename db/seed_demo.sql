-- Datos de demostración no aprobados para uso clínico.
-- Este archivo nunca se ejecuta como parte de las migraciones.
BEGIN;

INSERT INTO plantilla_tratamiento (clave, version_catalogo, nombre, clave_especialidad, duracion_clinica, espaciado)
SELECT
  CASE WHEN n = 1 THEN 'general.profilaxis' ELSE 'plantilla.' || lpad(n::text, 3, '0') END,
  '2026-09-16.1',
  CASE WHEN n = 1 THEN 'Profilaxis dental' ELSE 'Tratamiento de referencia ' || n END,
  (ARRAY['GENERAL','ENDODONCIA','ORTODONCIA','PERIODONCIA','PROSTODONCIA','CIRUGIA','ODONTOPEDIATRIA','IMPLANTOLOGIA','ESTETICA','RADIOLOGIA'])[((n - 1) % 10) + 1],
  CASE WHEN n = 1 THEN 30 ELSE 20 + ((n * 5) % 100) END,
  10
FROM generate_series(1,100) AS n
ON CONFLICT DO NOTHING;

INSERT INTO material_sugerido_plantilla (identificador_plantilla, nombre_generico, orden)
SELECT identificador, 'Guantes y material desechable', 1 FROM plantilla_tratamiento
ON CONFLICT DO NOTHING;

COMMIT;
