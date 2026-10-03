# Trazabilidad pantalla → endpoint

Estado: candidato de revisión ARQ-03.

| Pantalla o flujo | Operaciones principales |
|---|---|
| Crear cuenta | `POST /autenticacion/registro` |
| Iniciar sesión | `POST /autenticacion/inicio-sesion` |
| Recuperar sesión | `POST /autenticacion/renovacion`, `GET /autenticacion/usuario-actual` |
| Cerrar sesión | `POST /autenticacion/cierre-sesion` |
| Onboarding | `GET` y `PUT /onboarding` más catálogos relacionados |
| Inicio | `GET /inicio/resumen` |
| Perfil y consultorio | Operaciones de `/cuenta/perfil` y `/cuenta/organizacion` |
| Tiempo y capacidad | Operaciones de `/capacidad` |
| Gastos y equipos | Colecciones `/gastos`, `/equipos` y `/costos-indirectos/resumen` |
| Insumos | Colección `/insumos`, precios, archivo y restauración |
| Datos mensuales | Colección `/periodos-mensuales`, correcciones, anulación y restauración |
| Plantillas | `GET /plantillas-tratamiento` e importación definida en el contrato |
| Tratamientos | Colección `/tratamientos`, configuración, materiales, archivo y restauración |
| Vista previa | `POST /tratamientos/{identificador}/vista-previa` |
| Calcular y guardar | `POST /tratamientos/{identificador}/calculos` |
| Historial | `GET /tratamientos/{identificador}/historial` y detalle de hoja |
| Suscripción | Pantalla informativa del frontend; no consume un endpoint en el MVP |
| Ayuda | Contenido estático del frontend mientras no exista un servicio aprobado |

Los nombres exactos, parámetros, cuerpos y respuestas autoritativos son los definidos en `openapi.yaml`.
