# Medalyze Backend

API REST de Medalyze: calcula el costo de un tratamiento dental y sugiere
un precio con margen, a partir de los gastos indirectos, la capacidad de
atención, el tiempo clínico y los materiales del consultorio.

## Responsabilidades

- Autenticación y sesión (JWT de acceso + token de actualización).
- Cuenta, onboarding y perfil de capacidad del consultorio.
- Registro de gastos, equipos e insumos.
- Captura y corrección de datos mensuales de consumo.
- Motor de costeo: cálculo y guardado de hojas de costos.
- Contrato de API (OpenAPI) consumido por `Medalyze-FRONTEND`.

Las fórmulas oficiales de costeo viven en `app/domain/costeo/`, en Python
puro, sin depender de FastAPI ni de la base de datos — ver
`docs/adr/ADR-001-arquitectura-backend.md`.

## Documentación

| Carpeta | Contenido |
|---|---|
| `docs/adr/` | Decisiones de arquitectura (ADR). |
| `docs/arquitectura/` | Tabla de responsabilidad de cada clase del motor de costos. |
| `diagramaC4/C3/` | Diagrama C4 nivel 3 de los componentes de la API. |
| `docs/api/` | Contrato OpenAPI y convenciones (ARQ-03). |
