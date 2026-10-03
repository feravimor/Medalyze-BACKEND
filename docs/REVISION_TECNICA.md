# Revisión técnica del entregable

Fecha de corte: 3 de octubre de 2026.

## Alcance materializado

- ARQ-03: contrato OpenAPI 3.1, convenciones, errores, ejemplos y seguridad Bearer.
- BE-01: repositorio ejecutable, imagen de API, PostgreSQL 16, Compose, CI y endpoints de salud.
- BE-02: esquema reproducible mediante Alembic 1.16.5, catálogos semilla, restricciones, índices, historial, RLS y rol de aplicación.
- BE-03 a BE-10: las 56 operaciones de las 44 rutas del contrato tienen una ruta FastAPI implementada.
- Motor de costeo: cálculo con `Decimal`, bloqueos de dominio, snapshots e historial.
- Persistencia: SQLAlchemy 2.0.43 síncrono y psycopg 3.2.9, conforme a la arquitectura previa verificada.

## Evidencia automatizada local

| Control | Resultado |
|---|---|
| Ruff | Sin hallazgos |
| mypy | Sin hallazgos en 28 archivos de aplicación |
| Compilación Python | Correcta |
| OpenAPI | 44 rutas y 56 operaciones; referencias válidas |
| Correspondencia contrato/código | 56 de 56 operaciones |
| Tipos TypeScript | Generación correcta con `openapi-typescript` 7.10.1 |
| pytest | 11 pruebas aprobadas |
| Análisis sintáctico PostgreSQL | 99 sentencias de esquema y 7 de semilla analizadas |

## Límites de esta entrega

- Es un candidato para Pull Request, no una aprobación de producción.
- El entorno usado para preparar el ZIP no tenía daemon Docker ni servidor PostgreSQL. El workflow de CI incluido ejecuta `schema.sql` y `seed.sql` contra PostgreSQL 16; ese job debe quedar verde en GitHub antes del merge.
- La tarjeta BE-02 dice 22 tablas, pero el PUML de base de datos contiene 26 entidades. Se conservaron las 26 y se añadió una tabla técnica para idempotencia. El ingeniero debe aprobar esta diferencia.
- La cookie `HttpOnly` para el refresh token y la retención de idempotencia de 24 horas siguen siendo decisiones pendientes indicadas en el README.
- La pantalla de suscripción permanece informativa y fuera del contrato backend del MVP.
- Las pruebas incluidas validan reglas centrales, arquitectura, salud y correspondencia del contrato. Antes de producción deben ampliarse con integración transaccional por módulo, concurrencia, RLS entre dos organizaciones y recorridos E2E.

## Criterio recomendado para aceptar el PR

1. CI en verde con PostgreSQL 16 real.
2. Revisión del contrato por frontend y backend.
3. Confirmación de fórmulas y redondeos con los casos del manual funcional.
4. Prueba explícita de aislamiento entre dos organizaciones.
5. Aprobación de las decisiones pendientes y protección de `main`.
