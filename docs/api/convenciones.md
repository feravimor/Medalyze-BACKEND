# Convenciones de la API Medalyze v1.0

Estado: `Propuesto para revisión en ARQ-03`

## Versionado y URL base

- OpenAPI 3.1.0.
- Base de negocio: `/api/v1`.
- Rutas, campos JSON, códigos y mensajes de negocio en español.
- Los cambios incompatibles requieren una nueva versión mayor.
- Tras aprobar ARQ-03, cualquier cambio al contrato se realiza mediante Pull Request.

## Identificadores y tipos

- Identificadores públicos: UUID en el campo `identificador`.
- Fechas: `YYYY-MM-DD`; instantes: RFC 3339 con zona horaria.
- Meses: primer día del mes, `YYYY-MM-01`.
- Moneda: importes decimales serializados como cadenas, por ejemplo `"70.83"`, acompañados por `codigo_moneda` cuando el contexto no lo determine.
- Porcentajes: decimal de 0 a 100 salvo rangos específicos; no fracción de 0 a 1.
- Revisiones: entero no negativo expuesto como `revision` y enviado con `If-Match` en escrituras que lo exijan.

## Autenticación y sesión

- El token de acceso es JWT, dura 15 minutos y se envía con `Authorization: Bearer <token>`.
- El token de actualización es opaco, dura 7 días, se almacena sólo como hash en el servidor y rota en cada renovación.
- La reutilización de un token rotado/revocado invalida las sesiones de actualización del usuario.
- La propuesta preferida es transportar el token de actualización en cookie `HttpOnly`, `Secure` y `SameSite` acordado. Esta decisión debe aprobarse junto con CORS y CSRF antes de aceptar ARQ-03.
- `POST /autenticacion/cierre-sesion` revoca la sesión del servidor.

## Autorización y aislamiento

- La organización se deriva de la sesión; el cliente no elige libremente `identificador_organizacion`.
- Recurso inexistente o perteneciente a otra organización: 404 `NO_ENCONTRADO`.
- Usuario de la organización sin rol suficiente: 403 `SIN_PERMISO`.
- PostgreSQL aplica RLS; el frontend nunca se considera una barrera de seguridad.

## Paginación

Las colecciones que puedan crecer utilizan:

```http
GET /recurso?limite=20&cursor=<opaco>
```

```json
{
  "elementos": [],
  "siguiente_cursor": null
}
```

El cursor es opaco. El cliente no lo interpreta ni construye. Los catálogos pequeños pueden retornar una lista completa cuando OpenAPI lo declare expresamente.

## Concurrencia

- Las escrituras editables usan `If-Match: "<revision>"`.
- Si falta una revisión obligatoria: 428 `REVISION_REQUERIDA`.
- Si no coincide: 409 `CONFLICTO_REVISION` con `revision_actual`.
- Una mutación no se reintenta automáticamente desde el cliente.

## Idempotencia

`Idempotency-Key` es obligatoria en:

- `POST /tratamientos`;
- `POST /tratamientos/{identificador}/calculos`.

La clave se evalúa dentro del contexto de organización, usuario y operación. Repetir la misma clave con el mismo cuerpo devuelve el resultado original; reutilizarla con un cuerpo distinto produce conflicto. La retención exacta es una decisión pendiente de ARQ-03.

## Errores

Todos los errores usan el mismo envelope:

```json
{
  "detalle": {
    "codigo": "ERROR_VALIDACION",
    "mensaje": "Revisa los datos enviados.",
    "campos": [
      {"campo": "duracion_clinica", "mensaje": "Debe estar entre 1 y 600."}
    ],
    "bloqueos": [],
    "revision_actual": null,
    "request_id": "01J..."
  }
}
```

Los campos opcionales sólo aparecen cuando aplican. El catálogo estable incluye:

| HTTP | Código |
|---:|---|
| 401 | `CREDENCIALES_INVALIDAS`, `SIN_AUTENTICACION`, `TOKEN_VENCIDO` |
| 403 | `SIN_PERMISO` |
| 404 | `NO_ENCONTRADO` |
| 409 | `CORREO_YA_REGISTRADO`, `INSUMO_EN_USO`, `INSUMO_DUPLICADO`, `PERIODO_YA_REGISTRADO`, `CONFLICTO_REVISION` |
| 422 | `ERROR_VALIDACION`, `CALCULO_BLOQUEADO` |
| 428 | `REVISION_REQUERIDA` |
| 500 | `ERROR_INTERNO` |

Un 500 no expone trazas, secretos ni detalles internos. El `request_id` permite correlacionar logs.

## Bloqueos de cálculo

La API retorna código estable, paso y datos mínimos; el frontend decide el texto de navegación y la ruta de corrección.

| Código | Paso | Corrección en frontend |
|---|---:|---|
| `GASTO_NEGATIVO` | 1 | `/datos/costos` |
| `EQUIPO_INCOMPLETO` | 2 | `/datos/costos` |
| `SIN_COSTOS_INDIRECTOS_REGISTRADOS` | 3 | `/datos/costos` |
| `SIN_PERFIL_CAPACIDAD` | 4 | `/datos/tiempo` |
| `SIN_TIEMPO_ATENCION` | 4 | `/datos/tiempo` |
| `DURACION_INVALIDA` | 5 | Editor, `datos-clinicos` |
| `ESPACIADO_FUERA_RANGO` | 5 | Editor, `datos-clinicos` |
| `SIN_METODO_MATERIALES` | 6 | Editor, `materiales` |
| `SIN_MESES_VALIDOS` | 6 | `/datos/mensuales` |
| `INSUMO_ESPECIFICO_INVALIDO` | 6 | Editor o `/datos/insumos` |
| `RECETA_INCOMPLETA` | 6 | Editor o `/datos/insumos` |
| `IMPORTE_MATERIALES_FALTANTE` | 6 | Editor, `materiales` |
| `MATERIALES_EN_CERO` | 6 | Editor, `materiales` |
| `AJUSTE_FUERA_RANGO` | 7 | Editor, `resumen` |

## Efectos y respuestas

- La vista previa no escribe ni crea hojas de costos.
- Un cálculo completo guarda una hoja inmutable y responde 201.
- Un cálculo bloqueado responde 422 sin hoja parcial.
- DELETE exitoso responde 204, salvo que el recurso retornado sea necesario según el contrato.
- El frontend sólo presenta “guardado” después de una respuesta exitosa.

## Validación automática

Comandos sugeridos al configurar CI:

```bash
npx @redocly/cli lint docs/api/openapi.yaml
npx openapi-typescript docs/api/openapi.yaml -o src/shared/api/schema.d.ts
```

Las versiones exactas se fijan en los archivos de dependencias de BE-01 y FE-01.

