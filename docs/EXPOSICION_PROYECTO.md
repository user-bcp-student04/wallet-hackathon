# Guía de exposición: conciliación operativa de wallet

## 1. Objetivo de la exposición

Presentar el problema operativo, el MVP implementado y cómo se relacionan
producto, arquitectura, backend, frontend, pruebas y agente MCP. La demostración
debe usar datos sintéticos y dejar claro qué operaciones son de solo lectura y
cuáles persisten cambios.

**Duración sugerida:** 8–12 minutos.

## 2. Guion sugerido

### Apertura (1 minuto)

> “Una operación de wallet deja rastros en varias fuentes: la intención de pago,
> la respuesta del proveedor y el asiento del ledger. Si esas fuentes no
> coinciden, Operaciones necesita identificar el descalce, revisar evidencia y
> registrar su investigación sin alterar la regla financiera.”

Explicar que el alcance es un MVP local de conciliación para registros
normalizados. Los datos de demo son sintéticos; no representan movimientos
financieros reales ni conectan con proveedores reales.

### Problema y resultado (1 minuto)

Mostrar la [historia de usuario](./hu-operations-transaction-reconciliation.sp.md)
y la [épica](./epic-peru-wallet-mvp.sp.md). Resumir el resultado:

- Comparar wallet, provider y ledger por referencia.
- Detectar y presentar diferencias.
- Consultar resúmenes operativos.
- Dar seguimiento manual a incidencias con trazabilidad básica.

### Arquitectura y responsabilidades (2 minutos)

```text
Persona operadora
   ├── Dashboard React/TypeScript
   │      └── API FastAPI ── SQLite
   └── Agente Wallet Reconciliation Operator
          └── tools MCP locales ── misma API FastAPI
```

- **Backend:** fuente de verdad para validación, persistencia, reglas,
  unicidad y conteos.
- **Frontend:** consulta la API, presenta reportes y permite acciones manuales.
- **MCP/agente:** facilita consultas y puede solicitar una corrida solo cuando
  la persona lo pide explícitamente.
- **Reglas deterministas:** la IA no decide si una transacción concilia ni
  modifica registros.

### Funcionalidad y límites (1 minuto)

Explicar que se identifican registros faltantes o duplicados, diferencias de
canal/monto/moneda y resultados de proveedor no exitosos. El estado `PENDING`
del proveedor se clasifica como incidencia; no hay una ventana SLA temporal.
Resolver exige nota y no hay reapertura.

La explicación de incidencias es determinista: separa hechos de hipótesis no
verificadas, limita evidencia actual a 20 filas por fuente y puede ser
inconclusa. Es de solo lectura. No hay scheduler ni autenticación en esta
versión.

## 3. Preparación de la demo

### Requisitos

- Windows, Python 3.12 o superior y Node.js/npm.
- Dependencias backend instaladas en `backend\.venv`.
- Dependencias frontend instaladas en `frontend\node_modules`.
- VS Code con Copilot Chat habilitado para la parte del agente.
- La API local y la base SQLite disponibles.

No borres `backend\wallet.db` para preparar la exposición. La base puede
contener corridas ya realizadas; el seed de desarrollo es idempotente y las
corridas persisten entre reinicios.

### Terminal 1: iniciar el backend

Desde la raíz del repositorio:

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload
```

La API debe iniciar en `http://127.0.0.1:8000`. Verifica la documentación en
`http://127.0.0.1:8000/docs`. El seed local proporciona datos sintéticos para
los cinco días calendario completos anteriores en `America/Lima`; no crea
corridas automáticamente.

### Terminal 2: iniciar el frontend

Desde una segunda terminal en la raíz:

```powershell
cd frontend
npm install
npm run dev
```

Abre la URL de Vite, normalmente `http://127.0.0.1:5173`. El proxy `/api` y
`/health` apunta al backend local en el puerto 8000. Si las dependencias del
frontend ya fueron instaladas, basta con `npm run dev`.

### Habilitar el servidor MCP en VS Code

1. Asegúrate de que el backend esté activo.
2. Abre la vista de servidores MCP de VS Code y carga o inicia el servidor
   `wallet-reconciliation` definido en [.vscode/mcp.json](../.vscode/mcp.json).
3. Si ya estaba iniciado antes de levantar el backend, reinícialo.
4. Comprueba que el agente **Wallet Reconciliation Operator** aparece en el
   selector de agentes de Copilot Chat.

El servidor MCP usa el intérprete `backend\.venv\Scripts\python.exe` y envía
solicitudes a `http://127.0.0.1:8000`. Si el entorno virtual está en otra ruta,
revisa la ruta configurada en `.vscode/mcp.json`.

## 4. Demo web paso a paso (3–4 minutos)

### Paso 1: presentar el dashboard

1. Abre `http://127.0.0.1:5173`.
2. Señala el indicador de conexión a la API, los filtros de fecha/canal y las
   tarjetas de resumen.
3. Usa el selector de fecha para escoger una fecha de demostración reciente.
   La disponibilidad sintética corresponde a los cinco días completos
   anteriores según Lima.
4. Explica que las métricas distinguen transacciones resueltas de incidencias
   resueltas; no son el mismo conteo.

Si la fecha seleccionada no muestra corridas, eso es normal: el seed genera
registros, pero **no ejecuta conciliaciones** al iniciar. Se puede elegir otra
fecha/canal con registros disponibles para la demostración.

### Paso 2: revisar una corrida

1. Selecciona un canal o deja “Todos los canales”.
2. Expande una corrida para mostrar su ID, transacciones y descalces.
3. Describe los estados `OPEN`, `IN_PROGRESS` y `RESOLVED`.
4. Muestra los tipos de incidencia y explica que las reglas de comparación
   pertenecen al backend.

### Paso 3: demostrar una acción manual (opcional)

La interfaz permite iniciar una corrida si hay datos y aún no existe una para
esa combinación fecha/canal. Antes de pulsar **Ejecutar conciliación**, verifica
esa condición con el historial o con la disponibilidad. Una corrida nueva se
persiste y no se elimina al cerrar el backend.

Para enseñar la importación, se puede mostrar el panel de JSON sin enviar nada.
Una carga real escribe registros en la base persistente; úsala solo en una base
de demostración aislada o tras acordar que los datos añadidos permanezcan.

La acción **Resolver** también cambia datos persistentes y requiere nota. Para
una exposición de solo lectura, no la pulses; explica que el cambio se confirma
en backend y se refleja en los conteos al actualizar el reporte.

## 5. Demo del agente MCP paso a paso (3–4 minutos)

En Copilot Chat, elige **Wallet Reconciliation Operator**. Usa primero
solicitudes explícitamente de solo lectura:

1. **Consultar datos disponibles**

   > Consulta la disponibilidad para el 2026-10-15. No ejecutes ninguna conciliación.

   El agente consulta la disponibilidad y debe limitarse a informar fuentes,
   canales y corridas existentes. Si la fecha no tiene datos, debe decirlo sin
   ejecutar nada.

2. **Consultar historial**

   > Muéstrame todas las conciliaciones realizadas, con fecha, canal, ID y resumen. No ejecutes ninguna conciliación.

   Debe usar la tool de historial, recorrer las páginas necesarias y no crear ni
   modificar corridas.

3. **Consultar un reporte o explicar una incidencia**

   > Consulta el reporte de la corrida [ID disponible] y resume sus métricas.

   o:

   > Explica la incidencia [ID disponible]. No cambies su estado.

   La explicación debe separar hechos, hipótesis no verificadas y recomendación,
   indicar que la evidencia es actual al momento de la consulta y declarar si
   el resultado es inconcluso. No cierra la incidencia.

4. **Ejecución manual (solo con autorización para persistirla)**

   Si la exposición quiere demostrar una corrida nueva, primero confirma que
   hay registros y que no existe ya una corrida para esa fecha/canal. Luego
   formula claramente:

   > Ejecuta la conciliación del [AAAA-MM-DD] para el canal [canal] y explícame el resultado.

   La respuesta debe indicar el ID y si la corrida se creó o ya existía. La
   corrida persiste. No repitas el mismo par fecha/canal: la API evita
   duplicados y MCP no debe intentar evadir esa regla.

## 6. Resultado de demo previamente observado

En una ejecución previa sobre la base local, la corrida QR del `2026-10-15`
tenía ID `3`: una transacción conciliada y dos incidencias abiertas,
`AMOUNT_MISMATCH` y `MISSING_PROVIDER_RESULT`. La base SQLite es persistente y
puede haber cambiado; antes de exponer, consulta el historial y verifica el
reporte actual. No presentes esos valores como garantizados en una instalación
nueva.

## 7. Cómo se organiza el trabajo con agentes y OpenSpec

El proyecto incluye roles para etapas distintas:

1. **PM/PO:** convierte necesidad, historia y épica en propuesta y specs
   verificables; no decide arquitectura.
2. **Architect:** convierte proposal/specs en diseño y luego tareas
   trazables; no implementa.
3. **Developer:** implementa tasks aprobadas, añade pruebas y valida antes de
   marcar una tarea completa.
4. **Testing:** verifica la implementación contra criterios y entrega
   evidencia, sin cambiar el comportamiento funcional.
5. **Security Analyst:** revisa riesgos con evidencia y detiene el flujo antes
   de remediación.
6. **Wallet Reconciliation Operator:** usa MCP para operaciones manuales
   expresamente solicitadas.

Prompts reutilizables del workspace:

- [PO: proposal y specs](../.github/prompts/po-proposal-spec.prompt.md)
- [Arquitecto: design](../.github/prompts/architect-design.prompt.md)
- [Arquitecto: tasks](../.github/prompts/architect-tasks.prompt.md)
- [Developer: implementar tasks](../.github/prompts/developer-implement-tasks.prompt.md)
- [Testing: verificar implementación](../.github/prompts/testing-implementation.prompt.md)
- [Seguridad: revisar implementación](../.github/prompts/security-implementation-validation.prompt.md)

Los flujos OpenSpec `opsx-*` completan las acciones de explorar, proponer,
aplicar, actualizar, sincronizar y archivar cambios.

Hay dos tipos de cambios OpenSpec en el repositorio:

- `backend-wallet-reconciliation-initial` y
  `frontend-wallet-operations-initial`: describen el alcance como trabajo
  propuesto y tienen tasks pendientes.
- `backend-wallet-reconciliation` y `frontend-wallet-operations`: registran
  retrospectivamente el comportamiento implementado con tasks completadas.

Los cambios `-initial` no demuestran una cronología histórica de autoría; son
una representación del alcance objetivo. Los cambios retrospectivos sirven
para documentar el comportamiento actual.

## 8. Pruebas y evidencia técnica

- Backend: desde `backend/`, con el entorno virtual activado, ejecutar
  `python -m pytest`.
- Frontend: desde `frontend/`, ejecutar `npm run build` para TypeScript y Vite.
- API: consultar `/docs`, `/redoc` y `/openapi.json`.
- Especificación vigente: [SDD de conciliación](./sdd/conciliacion-operativa/README.md).
- Hallazgos de Discovery: [docs/HALLAZGOS.md](./HALLAZGOS.md).

La guía de testing del agente está en
[openspec-testing](../.github/skills/openspec-testing/SKILL.md). La guía de
operación MCP está en
[wallet-reconciliation-operations](../.github/skills/wallet-reconciliation-operations/SKILL.md).

## 9. Seguridad y limitaciones para mencionar

- Los datos de demostración son sintéticos.
- La API de este MVP no implementa autenticación/autorización. Mantenerla en
  entorno local/autorizado; no exponerla públicamente.
- El resultado del MCP o la evidencia explicativa puede incorporarse al
  contexto de Copilot. No enviar evidencia transaccional a modelos si el
  entorno no está autorizado para procesarla.
- MCP no carga fuentes ni resuelve incidencias. La tool de ejecución solo se
  utiliza cuando una persona lo solicita.
- No hay scheduler, integraciones directas con proveedores, resolución
  automática, auditoría avanzada de actor ni reapertura de incidencias resueltas.

## 10. Cierre sugerido

> “El MVP automatiza la comparación repetible y facilita la operación, pero
> conserva los límites importantes: el backend decide los resultados, la
> explicación no inventa causa raíz, y las decisiones de investigación siguen
> siendo manuales. El siguiente paso es validar el flujo con el equipo y
> priorizar autenticación, auditoría e integración de fuentes reales como
> trabajo futuro.”
