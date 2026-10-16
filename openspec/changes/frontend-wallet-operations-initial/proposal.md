# Proposal

## Why

El equipo de operaciones necesita una vista clara para revisar conciliaciones diarias, detectar incidencias y registrar el avance de su investigación. Un panel conectado a la API permitirá ejecutar el flujo operativo manualmente y comprender los resultados sin recurrir a consultas directas a la base de datos.

## What Changes

- Construir un panel que permita filtrar reportes por fecha y canal y consultar un resumen de actividad.
- Presentar por separado transacciones revisadas, conciliadas, por investigar, transacciones resueltas e incidencias resueltas.
- Mostrar corridas diarias expandibles con sus incidencias y datos principales.
- Permitir iniciar manualmente una conciliación y cargar lotes JSON de wallet, provider o ledger.
- Permitir avanzar incidencias a investigación y resolverlas con una nota requerida.
- Informar estados de carga, conectividad, validación, errores y confirmaciones de las operaciones.
- Limitar el alcance a la vista diaria; no incluir historial general de corridas ni una interfaz de explicación determinista MCP.

## Capabilities

### New Capabilities

- `frontend/operations-dashboard`: experiencia visible para consultar y operar conciliaciones diarias mediante la API.

### Modified Capabilities

Ninguna. No hay especificaciones OpenSpec principales existentes que modificar.

## Impact

- Área de interfaz prevista: `frontend/src/`.
- Integración prevista: API de conciliación para consultar reportes y resumen, cargar fuentes, iniciar corridas y actualizar incidencias.
- Construcción y validación previstas: TypeScript, Vite y scripts del proyecto frontend.
- Fuera de alcance: historial global, explicación de incidencias, autenticación/roles, ejecución automática y cambios a reglas financieras o contratos del backend.
