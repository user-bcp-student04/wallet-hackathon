# Tasks

## 1. Estructura e integración API

- [ ] 1.1 Crear la aplicación frontend, configuración y estructura de vistas; verificar que inicia en desarrollo y compila con el build del proyecto.
- [ ] 1.2 Definir tipos y cliente API para reportes, resumen, carga de fuentes, ejecución y actualización de incidencias; verificar solicitudes y errores con pruebas apropiadas para el cliente.

## 2. Vista diaria y reportes

- [ ] 2.1 Implementar selección de fecha y canal y carga sincronizada del resumen y los reportes; verificar filtros, estado vacío y errores de consulta.
- [ ] 2.2 Implementar tarjetas para las cinco métricas separadas; verificar que el resumen agregado y el filtrado por canal usan sus conteos correspondientes.
- [ ] 2.3 Implementar tarjetas de corrida expandibles con detalle de incidencias; verificar la presentación de corridas con y sin descalces.

## 3. Operaciones manuales

- [ ] 3.1 Implementar el formulario para solicitar conciliaciones de fecha y canal; verificar solicitud exitosa, campos requeridos, progreso y respuesta de conflicto.
- [ ] 3.2 Implementar importación de arreglos JSON para wallet, provider y ledger; verificar JSON inválido/vacío, límite del lote y mensaje de resultado.
- [ ] 3.3 Implementar acciones para iniciar investigación y resolver con nota requerida; verificar validación local, actualización tras respuesta y ausencia de reapertura.

## 4. Retroalimentación y verificación

- [ ] 4.1 Implementar estados accesibles de carga, conexión, error y confirmación; verificar mensajes visibles en respuestas exitosas y fallidas.
- [ ] 4.2 Documentar cómo configurar el frontend y conectarlo con la API; verificar instrucciones de instalación, arranque y build.
- [ ] 4.3 Ejecutar el build de producción y verificar que TypeScript y Vite finalizan sin errores.
