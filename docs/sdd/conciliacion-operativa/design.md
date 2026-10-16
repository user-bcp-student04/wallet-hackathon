# Diseño técnico implementado: conciliación operativa

## 1) Arquitectura actual

La solución está implementada en dos capas:

- **Backend API** en [backend/app/main.py](../../../backend/app/main.py)
  con FastAPI, SQLAlchemy y SQLite.
- **Frontend web** en [frontend/src/App.tsx](../../../frontend/src/App.tsx)
  con React + TypeScript.

La UI consume directamente los endpoints REST del backend (vía proxy de Vite en desarrollo).

## 2) Componentes backend

### 2.1 API HTTP

Definida en [backend/app/main.py](../../../backend/app/main.py):

- `GET /health`
- `POST /api/v1/records/{source}`
- `GET /api/v1/records/availability`
- `POST /api/v1/reconciliations`
- `GET /api/v1/reconciliations`
- `GET /api/v1/reconciliations/history`
- `GET /api/v1/reconciliations/daily-summary`
- `GET /api/v1/reconciliations/{run_id}`
- `GET /api/v1/discrepancies/{discrepancy_id}/explanation`
- `PATCH /api/v1/discrepancies/{discrepancy_id}`

### 2.2 Contratos y validación

Definidos en [backend/app/schemas.py](../../../backend/app/schemas.py) con Pydantic:

- Lotes de 1 a 1000 registros.
- `amount_minor > 0`.
- `currency` en formato `^[A-Z]{3}$`.
- `status` obligatorio para `provider`, prohibido para `wallet`/`ledger`.
- Para `RESOLVED`, `investigation_note` es obligatoria.

### 2.3 Modelo de persistencia

Definido en [backend/app/models.py](../../../backend/app/models.py):

- `source_records`
- `reconciliation_runs`
- `discrepancies`

Restricciones relevantes:

- unicidad de corrida por `reconciliation_date + channel`;
- unicidad de descalce por `run_id + transaction_reference + discrepancy_type`.

### 2.4 Motor de conciliación

Implementado en [backend/app/reconciliation.py](../../../backend/app/reconciliation.py):

1. filtra registros por fecha;
2. agrupa por `transaction_reference`;
3. selecciona solo referencias vinculadas al `channel` de la corrida;
4. evalúa reglas de faltantes/duplicados/mismatch y estado del proveedor;
5. incrementa `reconciled_count` cuando no hay hallazgos;
6. persiste descalces con estado inicial `OPEN`.

## 3) Reglas implementadas actualmente

Tipos de descalce:

- `MISSING_WALLET_RECORD`
- `MISSING_PROVIDER_RESULT`
- `MISSING_LEDGER_ENTRY`
- `DUPLICATE_WALLET_RECORD`
- `DUPLICATE_PROVIDER_RESULT`
- `DUPLICATE_LEDGER_ENTRY`
- `CHANNEL_MISMATCH`
- `AMOUNT_MISMATCH`
- `CURRENCY_MISMATCH`
- `PROVIDER_NOT_SUCCESSFUL`

Notas de comportamiento:

- Si el proveedor viene con `FAILED` o `PENDING`, se marca `PROVIDER_NOT_SUCCESSFUL`.
- No existe estado transaccional `PENDING` en resumen; se usa:
  - `reconciled_count`
  - `unreconciled_count`
  - `resolved_count` para transacciones con todos sus descalces resueltos
  - `resolved_discrepancy_count` para incidencias resueltas individualmente

## 4) Flujo funcional actual

1. Operaciones carga lotes por fuente, o el seed local genera datos sintéticos.
2. Operaciones o el agente MCP consulta la disponibilidad para la fecha/canal.
3. Operaciones ejecuta una corrida desde UI/API, o el agente lo hace solo por
   petición explícita y cuando los datos están disponibles.
4. Backend crea corrida y descalces detectados.
5. UI o MCP consulta el reporte y el resumen diario.
6. Operaciones actualiza descalces (`IN_PROGRESS` o `RESOLVED` con nota) desde
   la UI; MCP no cambia estados.

## 5) Estados de investigación

Estados soportados:

- `OPEN`
- `IN_PROGRESS`
- `RESOLVED`

Reglas:

- se puede pasar de `OPEN` a `IN_PROGRESS` o `RESOLVED`;
- se puede actualizar nota en transiciones válidas;
- no se puede reabrir un descalce ya `RESOLVED` (retorna `409`).

## 6) Diseño frontend

La pantalla principal en [frontend/src/App.tsx](../../../frontend/src/App.tsx):

- carga reportes y resumen diario en paralelo;
- muestra salud de API;
- ejecuta corrida con formulario de canal;
- permite carga JSON por fuente;
- renderiza descalces por corrida con acciones de investigación.

Cliente HTTP en [frontend/src/api.ts](../../../frontend/src/api.ts):

- tipado de respuestas;
- manejo de errores con `ApiError`;
- operaciones CRUD del flujo operativo.

## 7) Datos sintéticos y entorno

El seed está en [backend/app/demo_data.py](../../../backend/app/demo_data.py):

- asegura registros sintéticos de wallet, provider y ledger en cada uno de los
  cinco días completos anteriores a hoy en `America/Lima`;
- genera datos por fecha de forma idempotente, preserva registros existentes y
  no crea corridas;
- se desactiva en producción o con `SEED_DEMO_DATA=false`.

## 8) Agente y servidor MCP

El servidor [backend/app/mcp_server.py](../../../backend/app/mcp_server.py) usa
stdio y consume la API local existente. Expone herramientas para disponibilidad,
ejecución explícita, reporte de corrida y resumen diario. Comprueba que haya
datos antes de crear una corrida, y ante una corrida ya existente devuelve el
reporte en vez de duplicarla. `list_reconciliation_history` ofrece un listado
paginado de solo lectura, filtrable por rango de fechas y canal, con los
resúmenes de cada corrida; el agente recorre páginas hasta cubrir el total.

El agente [Wallet Reconciliation Operator](../../../.github/agents/reconciliation-operator.agent.md)
y la skill
[wallet-reconciliation-operations](../../../.github/skills/wallet-reconciliation-operations/SKILL.md)
definen un flujo manual con límites de operación. No cargan o editan fuentes ni
resuelven incidencias, y no incluyen scheduler.

Para explicar una incidencia, `get_discrepancy_explanation` consulta el endpoint
aditivo de solo lectura. Un catálogo determinista cubre cada `DiscrepancyType`;
la API limita la evidencia actual a 20 filas por fuente, informa truncamiento y
separa hechos, hipótesis no verificadas y recomendación. No existe snapshot de
las filas fuente al momento de la corrida: toda respuesta etiqueta su evidencia
como actual a la consulta. El resultado puede ser observado o inconcluso; no
establece causa raíz ni cambia estado. La UI existente permanece como flujo de
confirmación humana.

## 9) Cobertura de pruebas

Pruebas en:

- [backend/tests/test_reconciliation_api.py](../../../backend/tests/test_reconciliation_api.py)
- [backend/tests/test_demo_data.py](../../../backend/tests/test_demo_data.py)
- [backend/tests/test_mcp_server.py](../../../backend/tests/test_mcp_server.py)

Validan:

- conciliación exitosa;
- descalces por tipo;
- resolución de descalces y efecto en resumen;
- filtros por fecha/canal y resumen diario;
- validaciones de API y unicidad de corrida;
- disponibilidad de OpenAPI/docs;
- seed sintético, disponibilidad y garantías operativas de las herramientas MCP.

## 10) Limitaciones técnicas vigentes

- Sin autenticación/autorización.
- Sin historial de eventos de investigación por actor (solo estado actual y nota).
- Sin SLA temporal para diferenciar pendiente vs ausente definitivo.
- Sin integración nativa con sistemas externos reales.
