# Evidencia para cierre de tickets

Fecha de corte: 3 de octubre de 2026. Estado general: candidato para Draft Pull Request.

| Ticket | Evidencia incluida | Condición externa para cerrarlo |
|---|---|---|
| ARQ-03 | OpenAPI, convenciones, trazabilidad pantalla-endpoint, validador y generación TypeScript | Revisión conjunta frontend/backend y aprobación |
| BE-01 | FastAPI, Docker, Compose, salud, disponibilidad y CI | Workflow verde y staging del equipo |
| BE-02 | Alembic, esquema, semillas, 14 enums, RLS y pruebas PostgreSQL | Aprobar diferencia 22/26 entidades más tabla de idempotencia |
| BE-03 | Autenticación, sesión, cuenta, organización, onboarding y permisos | Pruebas de integración verdes y revisión de cookie/CSRF |
| BE-04 | Capacidad, gastos, equipos, resumen y datos sintéticos | CI PostgreSQL verde |
| BE-05 | Insumos, unidades, precios, archivo y restauración | CI PostgreSQL verde |
| BE-06 | Periodos, corrección, anulación, restauración y promedio | CI PostgreSQL verde |
| BE-07 | Plantillas, tratamientos, configuración y materiales | CI PostgreSQL verde |
| BE-08 | Vista previa, cálculo, idempotencia, revisión y bloqueos | Validación funcional con frontend |
| BE-09 | Hojas, snapshots e historial aislado | Prueba RLS y rollback verde |
| BE-10 | Resumen de inicio | Revisión de campos requeridos por frontend |
| CAL-01–CAL-07 | Tipos de valor, bloqueos, fórmulas, siete puertos, adaptadores, banco del manual, Hypothesis y cobertura 93 % | Revisión matemática y aprobación técnica |

## Controles automáticos

- Ruff y mypy.
- Validación de 44 rutas y 56 operaciones OpenAPI.
- Correspondencia 56/56 entre contrato e implementación.
- Generación de tipos TypeScript.
- Compilación del C3.
- Banco de escenarios B, R, A y límites L del manual.
- Propiedades del redondeo al múltiplo de 50.
- Cobertura del dominio con mínimo obligatorio de 90 %.
- PostgreSQL 16 real: migraciones, RLS entre dos organizaciones, rol no superusuario y rollback.

## Regla de cierre

El código y la evidencia permiten mover los tickets a **En revisión**. Sólo se mueven a **Done** cuando el workflow esté verde, el Pull Request tenga aprobación y las decisiones abiertas queden resueltas por el responsable técnico.
