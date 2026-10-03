# Alcance funcional del MVP

Medalyze es un sistema de costeo para consultorios dentales. El backend cubre autenticación, cuenta y organización, onboarding, capacidad, gastos, equipos, insumos, periodos mensuales, plantillas, tratamientos, costeo, historial e inicio.

## Suscripción

La ruta frontend `/cuenta/suscripcion` se conserva como pantalla informativa. En el MVP no existen planes comerciales, cobros, pagos, facturas de suscripción, renovaciones ni cancelaciones. Por ello ARQ-03 no publica endpoints de suscripción y el esquema no crea tablas para esta capacidad.

Esta delimitación evita presentar una navegación prevista como una función ya respaldada por el servidor. Cualquier monetización futura debe entrar mediante un ticket, actualización de ADR, cambios en OpenAPI y revisión de seguridad.

## Fuera de alcance

Los ADR actuales tampoco definen pacientes, agenda de citas, expediente clínico, odontograma, cobranza a pacientes, facturación fiscal, nómina ni inventario físico con entradas y salidas.
