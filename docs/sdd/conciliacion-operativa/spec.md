# Especificación funcional actual (alineada a implementación)

## 1) Glosario operativo

- **Corrida**: ejecución de conciliación para una `reconciliation_date` y un `channel`.
- **Referencia transaccional**: clave usada para agrupar registros entre fuentes.
- **Descalce**: hallazgo de inconsistencia o ausencia detectada por reglas.
- **Estado de investigación**: ciclo operativo de un descalce (`OPEN`, `IN_PROGRESS`, `RESOLVED`).

## 2) Requisitos funcionales implementados

### RF-01 Carga de registros fuente

El sistema permite cargar registros normalizados por fuente (`wallet`, `provider`, `ledger`)
mediante `POST /api/v1/records/{source}`.

### RF-02 Reglas de validación de carga

- El lote debe tener entre 1 y 1000 registros.
- `provider` requiere `status`.
- `wallet` y `ledger` no admiten `status`.
- `amount_minor` debe ser entero positivo.
- `currency` debe tener 3 letras mayúsculas.

### RF-03 Ejecución de conciliación

El sistema ejecuta una corrida con `POST /api/v1/reconciliations` para una fecha y canal.
No se permite crear más de una corrida para la misma combinación `fecha + canal`.

### RF-04 Detección de tipos de descalce

La corrida detecta:

- faltantes por fuente;
- duplicados por fuente;
- diferencia de canal;
- diferencia de monto;
- diferencia de moneda;
- resultado de proveedor no exitoso (`FAILED` o `PENDING`).

### RF-05 Resumen por corrida

Cada corrida devuelve:

- `transaction_count`
- `reconciled_count`
- `unreconciled_count`
- `resolved_count` (transacciones con descalces y todos resueltos)
- `resolved_discrepancy_count` (incidencias en estado `RESOLVED`)

### RF-06 Consulta de reportes

`GET /api/v1/reconciliations` devuelve corridas de una fecha, opcionalmente filtradas por canal,
incluyendo descalces y resumen de cada corrida.

### RF-07 Resumen diario agregado

`GET /api/v1/reconciliations/daily-summary` agrega resultados de todas las corridas del día e
incluye la lista de canales procesados. Mantiene separados los conteos de transacciones
resueltas (`resolved_count`) e incidencias resueltas (`resolved_discrepancy_count`).

### RF-08 Consulta de corrida individual

`GET /api/v1/reconciliations/{run_id}` devuelve una corrida específica o `404` si no existe.

### RF-09 Gestión de investigación de descalces

`PATCH /api/v1/discrepancies/{discrepancy_id}` permite:

- pasar a `IN_PROGRESS`;
- resolver (`RESOLVED`) con nota obligatoria;
- actualizar nota cuando corresponda.

### RF-10 Restricción de reapertura

Si un descalce ya está en `RESOLVED`, no puede volver a `OPEN`/`IN_PROGRESS` (`409`).

### RF-11 Disponibilidad de datos para conciliación

`GET /api/v1/records/availability` informa, para una fecha operativa, el conteo
de registros por fuente y canal y si ya existe una corrida. No expone referencias
transaccionales.

### RF-12 Datos sintéticos de demostración

En desarrollo, al iniciar la API se aseguran registros sintéticos para los cinco
días calendario completos anteriores en `America/Lima`. El seed es idempotente,
conserva registros existentes y no crea corridas. Se desactiva en producción o
con `SEED_DEMO_DATA=false`.

### RF-13 Operación manual mediante agente MCP

El servidor MCP local permite consultar disponibilidad, solicitar una corrida,
consultar su reporte y obtener el resumen diario. Ejecuta mediante la API
existente; requiere petición explícita del usuario, no crea corridas sin datos
y devuelve la corrida existente cuando ya existe. No carga ni modifica registros
fuente o estados de investigación. No hay scheduler.

### RF-14 Historial paginado de corridas

`GET /api/v1/reconciliations/history` lista las corridas existentes ordenadas de
la más reciente a la más antigua. Acepta filtros inclusivos opcionales
`start_date` y `end_date`, filtro exacto opcional `channel`, y paginación por
`limit` (1-100; predeterminado 50) y `offset` (predeterminado 0). Devuelve el
total de resultados filtrados y elementos con ID, fecha, canal, fecha de
creación y resumen, sin incluir detalle de incidencias. Es de solo lectura.

### RF-15 Explicación determinista de una incidencia

`GET /api/v1/discrepancies/{id}/explanation` devuelve, para uno de los diez tipos
de incidencia vigentes, el estado de evaluación (`OBSERVED` o `INCONCLUSIVE`),
hechos obtenidos de la evidencia fuente actual, hipótesis etiquetadas como no
verificadas y una recomendación manual. Consulta como máximo 20 filas por fuente
para la referencia y fecha de la incidencia; los conteos informan el total y si
la muestra fue truncada. Si se trunca o no alcanza la evidencia, el resultado es
inconcluso. Incluye el momento de consulta y advierte que no es un snapshot de la
corrida original. La consulta no cambia fuentes, incidencias, estados, notas ni
métricas. La persona analista verifica la evidencia y gestiona cualquier
transición por el flujo actual.

## 3) Requisitos no funcionales implementados

- **NFR-01 Trazabilidad mínima**: cada descalce conserva referencia, tipo, detalle, timestamps y nota.
- **NFR-02 Documentación API**: OpenAPI disponible en `/openapi.json` y UI en `/docs` y `/redoc`.
- **NFR-03 Determinismo básico**: reglas de conciliación codificadas y reproducibles sobre los mismos datos.
- **NFR-04 Persistencia local**: SQLite con creación automática de tablas.
- **NFR-05 Fecha operativa de demostración**: los días sintéticos se determinan
  con la zona horaria `America/Lima`.
- **NFR-06 Integridad de operación MCP**: el backend es la fuente de verdad;
  MCP no omite las validaciones ni la unicidad fecha/canal de la API.

## 4) Comportamientos validados por pruebas

Los tests en [backend/tests/test_reconciliation_api.py](../../../backend/tests/test_reconciliation_api.py),
[backend/tests/test_demo_data.py](../../../backend/tests/test_demo_data.py) y
[backend/tests/test_mcp_server.py](../../../backend/tests/test_mcp_server.py) cubren:

1. conciliación correcta cuando las tres fuentes coinciden;
2. detección de faltantes y resolución de descalces;
3. detección de duplicados y diferencias de monto;
4. cobertura del catálogo de tipos de descalce;
5. filtros por fecha/canal y resumen diario agregado;
6. errores esperados (`422`, `404`, `409`);
7. exposición del contrato OpenAPI;
8. disponibilidad de datos, seed de cinco días e idempotencia sin crear corridas;
9. protección contra corridas sin datos y duplicados a través de tools MCP.

## 5) Diferencias entre diseño ideal y estado actual

- No existe aún un estado de conciliación “pendiente por SLA temporal”.
- `provider=PENDING` se considera descalce inmediato (`PROVIDER_NOT_SUCCESSFUL`).
- No hay auditoría de actor por cambio de estado.
- No hay control de acceso en endpoints.
