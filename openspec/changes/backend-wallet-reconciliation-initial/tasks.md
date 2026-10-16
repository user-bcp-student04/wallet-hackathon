# Tasks

## 1. Base del servicio y persistencia

- [ ] 1.1 Crear la estructura del backend, configuración y modelos persistentes; verificar que el servicio inicializa el esquema en una base de datos temporal.
- [ ] 1.2 Definir schemas de entrada y salida para fuentes, corridas, incidencias y resúmenes; verificar los casos válidos y los errores de validación con pruebas unitarias.

## 2. Ingesta y motor de conciliación

- [ ] 2.1 Implementar la carga validada de wallet, provider y ledger; verificar límite de lote, campos por fuente y persistencia mediante pruebas de API.
- [ ] 2.2 Implementar comparación determinista por referencia, clasificación de faltantes/duplicados/diferencias y unicidad fecha-canal; verificar tipos de resultado y conflicto duplicado con pruebas de conciliación.
- [ ] 2.3 Documentar el formato de registros y ejecución de conciliaciones; verificar que los ejemplos de la guía pasan las validaciones de API.

## 3. Investigación, reportes y consultas operativas

- [ ] 3.1 Implementar estados de incidencia, nota obligatoria para resolver y restricción de reapertura; verificar transiciones y errores con pruebas de API.
- [ ] 3.2 Implementar reportes, resumen diario y métricas separadas de transacciones e incidencias resueltas; verificar agregaciones con pruebas de API.
- [ ] 3.3 Implementar disponibilidad e historial filtrado y paginado; verificar filtros, orden y límites con pruebas de API.
- [ ] 3.4 Documentar los contratos de reporte, resumen, disponibilidad e historial; verificar ejemplos contra los schemas de respuesta.

## 4. Explicaciones deterministas

- [ ] 4.1 Implementar la evaluación por tipo de incidencia con hechos, hipótesis no verificadas y recomendación manual; verificar los tipos soportados con pruebas.
- [ ] 4.2 Acotar la evidencia a 20 filas por fuente y responder inconcluso ante insuficiencia o truncamiento; verificar límites y evaluación con pruebas de API.
- [ ] 4.3 Verificar que una explicación no modifica fuentes, estados, notas ni métricas, y documentar que la evidencia es actual al momento de consulta.

## 5. Entorno local y herramientas MCP

- [ ] 5.1 Implementar seed sintético idempotente para los cinco días completos anteriores en `America/Lima`; verificar idempotencia, conservación de registros y ausencia de corridas en pruebas.
- [ ] 5.2 Implementar tools MCP para disponibilidad, reportes, resumen, historial, explicación y ejecución manual explícita; verificar delegación a la API y ausencia de escrituras no autorizadas mediante pruebas MCP.
- [ ] 5.3 Documentar instalación local, configuración del MCP y límites operativos; verificar los comandos de instalación y arranque en una instalación limpia.

## 6. Verificación integrada

- [ ] 6.1 Ejecutar la suite backend completa y verificar que todas las pruebas de API, seed y MCP pasan en el entorno configurado.
