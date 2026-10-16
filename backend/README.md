# Wallet reconciliation API

FastAPI + SQLite implementation of the MVP's daily operational reconciliation story.
SQLite stores normalized wallet transactions, provider results, ledger records, runs,
and discrepancy investigation status. The initial input contract is a JSON batch API;
provider and ledger integrations can map their source formats to this canonical shape.

## Levantar el backend en local

Desde la raíz del repositorio, abre una terminal para el backend:

```powershell
cd backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
uvicorn app.main:app --reload
```

En Windows, la dependencia `tzdata` se instala automáticamente junto con el
proyecto y proporciona la base de zonas horarias que Python necesita para
resolver `America/Lima`. Si ya tenías creado el entorno virtual antes de que se
agregara esta dependencia, vuelve a ejecutar `python -m pip install -e ".[dev]"`
desde `backend` con ese entorno activado antes de iniciar la API.

Uvicorn queda escuchando por defecto en `http://127.0.0.1:8000`. La base SQLite se
crea en `backend/wallet.db` si no existe; se puede cambiar mediante `DATABASE_URL`.
En desarrollo, cada inicio asegura datos **sintéticos** para los cinco días
calendario completos anteriores en `America/Lima`, con ejemplos QR y P2P de
coincidencias y descalces. El seed es idempotente por fecha, conserva los registros
existentes y **no crea corridas**: el usuario o el agente MCP las solicita
explícitamente. El seed se desactiva en producción y puede apagarse localmente
con `SEED_DEMO_DATA=false`.
La documentación interactiva está en [Swagger UI](http://127.0.0.1:8000/docs) y
[ReDoc](http://127.0.0.1:8000/redoc); el contrato OpenAPI JSON está en
`http://127.0.0.1:8000/openapi.json`.

Para desactivar los datos de ejemplo durante el desarrollo, antes de iniciar Uvicorn:

```powershell
$env:SEED_DEMO_DATA = "false"
uvicorn app.main:app --reload
```

El seed queda desactivado automáticamente con `APP_ENV=production`; los datos de
demostración no se deben utilizar como registros financieros reales.

Para los siguientes inicios, con el entorno virtual activo, basta con:

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload
```

## Funcionalidad de la API

- `POST /api/v1/records/wallet`, `/provider`, `/ledger`: guarda lotes de hasta 1,000
  registros normalizados. Los montos son enteros en unidades menores; para PEN, céntimos.
- `GET /api/v1/records/availability?reconciliation_date=AAAA-MM-DD`: devuelve por canal
  los conteos de registros por fuente y si ya existe una corrida, sin exponer referencias.
- `POST /api/v1/reconciliations`: crea una corrida diaria para una fecha y un canal.
- `GET /api/v1/reconciliations?reconciliation_date=AAAA-MM-DD&channel=qr`: consulta
  reportes filtrados por fecha y, opcionalmente, canal.
- `GET /api/v1/reconciliations/history`: lista todas las corridas existentes de la
  más reciente a la más antigua. Acepta `start_date`, `end_date` (inclusivas),
  `channel`, `limit` (1-100, por defecto 50) y `offset` para paginar.
- `GET /api/v1/reconciliations/daily-summary?reconciliation_date=AAAA-MM-DD`: agrega
  los totales y canales de todas las corridas del día.
- `GET /api/v1/reconciliations/{run_id}`: consulta el resumen y detalle de descalces.
- `GET /api/v1/discrepancies/{id}/explanation`: devuelve evidencia fuente actual
  (hasta 20 filas por fuente), hechos, hipótesis no verificadas y una recomendación
  determinista. No es un snapshot de la corrida ni modifica estado o registros.
- `PATCH /api/v1/discrepancies/{id}`: actualiza el estado de investigación y su nota.

The reconciliation compares records by transaction reference and expects at most one
normalized record per source/reference/date. Duplicate source rows, missing records,
channel/amount/currency mismatches, and non-successful provider outcomes are reported.
Esta versión crea una sola corrida por fecha y canal; los flujos de repetición y
corrección, límites específicos de proveedores, autenticación y reglas de normalización
del ledger deben definirse antes del uso en producción.

Los resúmenes cuentan referencias de transacción distintas: conciliadas (sin descalces),
pendientes (con al menos un descalce no resuelto) y resueltas (con descalces y todos
resueltos). `resolved_discrepancy_count` cuenta por separado las incidencias resueltas;
no debe confundirse con `resolved_count`, que cuenta transacciones resueltas.

## Agente y MCP local

La configuración `.vscode/mcp.json` agrega el servidor MCP local
`wallet-reconciliation` por stdio. Conserva también el servidor `github-local`
preexistente. Para usarlo:

1. Crea/activa el entorno virtual e instala dependencias desde `backend/` con
   `python -m pip install -e ".[dev]"`.
2. En otra terminal inicia la API con `uvicorn app.main:app --reload`.
3. En VS Code reinicia el servidor MCP `wallet-reconciliation` desde la vista de
   servidores MCP si ya estaba iniciado.
4. Invoca el agente **Wallet Reconciliation Operator** y solicita una fecha o
   varias fechas. Puedes pedir canales específicos; si no indicas canales, el
   agente puede usar los canales que informe la consulta de disponibilidad.

Las tools disponibles son:

- `list_available_reconciliation_data`: consulta fuentes/canales disponibles y
  corridas existentes para una fecha.
- `run_reconciliation`: requiere datos para el canal solicitado; si ya hay
  corrida, devuelve esa corrida existente en vez de intentar duplicarla.
- `get_reconciliation_report`: consulta una corrida existente sin crearla.
- `get_daily_reconciliation_summary`: consulta el resumen diario.
- `list_reconciliation_history`: lista corridas existentes con filtros opcionales
  por rango de fechas y canal, y paginación (`limit`, `offset`). Devuelve fecha,
  canal, ID y resumen, sin detalle de incidencias.
- `get_discrepancy_explanation`: analiza de forma determinista una incidencia por ID
  y devuelve hechos, hipótesis, recomendación y evidencia actual, en modo solo lectura.

El MCP no carga datos, no cambia estados de investigación y no escribe en las
fuentes financieras. La API debe estar corriendo localmente; si está inaccesible,
la tool reporta el error explícitamente. No hay scheduler configurado: las
conciliaciones se ejecutan solo cuando el usuario lo solicita. Los datos demo
no son datos reales ni se deben usar para operaciones financieras.

El análisis de incidencias no determina causa raíz ni resuelve el caso. La evidencia
se obtiene en el momento de la consulta, puede incluir registros cargados después de
la corrida y se limita a 20 filas por fuente; una muestra truncada o insuficiente se
marca como inconclusa. Las hipótesis se presentan como no verificadas y toda acción
de resolución requiere validación humana en la UI/API. Si se invoca desde Copilot
Chat, la evidencia devuelta puede formar parte del contexto del modelo: usa esta
tool solo en un entorno autorizado para procesar esos datos. La API del MVP aún
no implementa autenticación/autorización; no expongas este endpoint a redes o
entornos productivos sin incorporar esos controles.

## Tests

```powershell
python -m pytest
```
