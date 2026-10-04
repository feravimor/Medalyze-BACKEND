# Revisión técnica del entregable

Fecha de corte: 3 de octubre de 2026.

## Alcance materializado

- ARQ-03: contrato OpenAPI 3.1, convenciones, errores, ejemplos y seguridad Bearer.
- BE-01: repositorio ejecutable, imagen de API, PostgreSQL 16, Compose, CI y endpoints de salud.
- BE-02: esquema reproducible mediante Alembic 1.16.5, catálogos semilla, restricciones, índices, historial, RLS y rol de aplicación.
- BE-03 a BE-10: las 56 operaciones de las 44 rutas del contrato tienen una ruta FastAPI implementada.
- Motor de costeo: cálculo con `Decimal`, bloqueos de dominio, snapshots e historial.
- Persistencia: SQLAlchemy 2.0.43 síncrono y psycopg 3.2.9, conforme a la arquitectura previa verificada.
- CAL-01 a CAL-07: tipos de valor, bloqueos, fórmulas, siete puertos, adaptadores, banco de escenarios, Hypothesis y cobertura del dominio ≥ 90 %.

## Evidencia automatizada local

| Control | Resultado |
|---|---|
| Ruff | Sin hallazgos |
| mypy | Sin hallazgos en 34 archivos de aplicación y scripts |
| Compilación Python | Correcta |
| OpenAPI | 44 rutas y 56 operaciones; referencias válidas |
| Correspondencia contrato/código | 56 de 56 operaciones |
| Tipos TypeScript | Generación correcta con `openapi-typescript` 7.10.1 |
| pytest local | 24 pruebas aprobadas; 3 de PostgreSQL omitidas fuera de CI |
| Cobertura del dominio | 93 %; mínimo obligatorio 90 % |
| C3 | Compilación correcta a PNG, 1636 × 912 px |
| Análisis sintáctico PostgreSQL | 99 sentencias de esquema y 7 de semilla analizadas |

## Límites de esta entrega

- Es un candidato para Pull Request, no una aprobación de producción.
- El entorno usado para preparar el ZIP no tenía daemon Docker ni servidor PostgreSQL. El workflow de CI ejecuta `alembic upgrade head` contra PostgreSQL 16 y habilita las tres pruebas de integración; ese job debe quedar verde antes del merge.
- La tarjeta BE-02 dice 22 tablas, pero el PUML de base de datos contiene 26 entidades. Se conservaron las 26 y se añadió una tabla técnica para idempotencia. El ingeniero debe aprobar esta diferencia.
- La cookie `HttpOnly` para el refresh token y la retención de idempotencia de 24 horas siguen siendo decisiones pendientes indicadas en el README.
- La pantalla de suscripción permanece informativa y fuera del contrato backend del MVP.
- Las pruebas incluidas validan reglas centrales, banco matemático, arquitectura, salud, contrato, rollback y RLS entre dos organizaciones. La concurrencia intensiva y los recorridos E2E corresponden a PRU-01/PRU-03 y permanecen fuera de este paquete backend.

## Criterio recomendado para aceptar el PR

1. CI en verde con PostgreSQL 16 real.
2. Revisión del contrato por frontend y backend.
3. Confirmar en CI el banco de fórmulas y redondeos contrastado con el manual.
4. Confirmar en CI las pruebas RLS, rol no superusuario y rollback.
5. Aprobación de las decisiones pendientes y protección de `main`.
