# Spec Delta

## Purpose

Define la experiencia del panel que permitirá al equipo consultar resultados diarios de conciliación y ejecutar manualmente las tareas de operación e investigación conectadas a la API.

## ADDED Requirements

### Requirement: Consulta diaria filtrable por fecha y canal

El panel SHALL permitir seleccionar una fecha y filtrar reportes por canal, reflejando los filtros seleccionados en la actividad y el resumen presentado.

#### Scenario: Consultar todos los canales de una fecha
- **WHEN** se selecciona una fecha con el filtro de canal en “Todos”
- **THEN** el panel presenta el resumen diario agregado y las corridas disponibles para esa fecha

#### Scenario: Filtrar por canal
- **WHEN** se selecciona un canal disponible en la fecha
- **THEN** el panel presenta el resumen de ese canal y solo sus reportes

#### Scenario: Fecha sin corridas
- **WHEN** la API no devuelve corridas para la fecha seleccionada
- **THEN** el panel presenta métricas en cero y una indicación de que no hay conciliaciones para esa fecha

### Requirement: Métricas diferenciadas en el resumen

El panel SHALL mostrar en unidades separadas transacciones revisadas, conciliadas, por investigar, transacciones resueltas e incidencias resueltas.

#### Scenario: Mostrar resumen agregado
- **WHEN** se carga el resumen sin filtro de canal
- **THEN** el panel presenta `transaction_count`, `reconciled_count`, `unreconciled_count`, `resolved_count` y `resolved_discrepancy_count` como métricas distintas

#### Scenario: Mostrar resumen por canal
- **WHEN** se selecciona un canal
- **THEN** las métricas representan ese canal y no el agregado diario de todos los canales

### Requirement: Exploración de reportes y descalces del día

El panel SHALL mostrar las corridas de la fecha seleccionada con canal, identificador, fecha, conteos y detalle expandible de descalces.

#### Scenario: Expandir una corrida con descalces
- **WHEN** se abre el detalle de una corrida que contiene incidencias
- **THEN** el panel muestra referencia, tipo, detalle, estado y acciones de investigación para cada incidencia

#### Scenario: Expandir una corrida conciliada
- **WHEN** se abre una corrida sin descalces
- **THEN** el panel indica que los movimientos comparados coinciden

### Requirement: Solicitud manual de conciliación

El panel SHALL permitir solicitar una corrida para la fecha seleccionada y un canal ingresado, mostrando el resultado de la operación.

#### Scenario: Solicitar corrida
- **WHEN** se envía el formulario con un canal no vacío
- **THEN** el panel solicita la corrida, presenta confirmación y actualiza los reportes y el resumen

#### Scenario: Canal vacío o solicitud en curso
- **WHEN** el canal está vacío o la solicitud ya está en curso
- **THEN** el control de ejecución permanece deshabilitado

#### Scenario: Corrida duplicada
- **WHEN** el backend responde que la combinación fecha y canal ya existe
- **THEN** el panel muestra el error y actualiza el reporte disponible

### Requirement: Carga manual de lotes JSON

El panel SHALL permitir seleccionar wallet, provider o ledger e importar un arreglo JSON no vacío con hasta 1000 registros, mostrando el resultado de la carga.

#### Scenario: Cargar arreglo válido
- **WHEN** se envía un arreglo JSON válido para una fuente
- **THEN** el panel informa la cantidad cargada y actualiza los datos que presenta

#### Scenario: Rechazar texto JSON inválido o arreglo vacío
- **WHEN** el contenido no es JSON válido, no es un arreglo o está vacío
- **THEN** el panel muestra un error y no comunica una carga exitosa

#### Scenario: Importar registros de provider
- **WHEN** se selecciona la fuente provider
- **THEN** el panel indica que cada registro requiere estado `SUCCESS`, `FAILED` o `PENDING`

### Requirement: Seguimiento manual de incidencias

El panel SHALL permitir avanzar incidencias abiertas a investigación y resolver incidencias no resueltas mediante una nota no vacía.

#### Scenario: Iniciar investigación
- **WHEN** se elige Investigar para una incidencia abierta
- **THEN** el panel solicita el estado `IN_PROGRESS` y actualiza el reporte cuando el backend confirma el cambio

#### Scenario: Resolver sin nota
- **WHEN** se elige Resolver con la nota vacía
- **THEN** el panel muestra una validación local y no envía la actualización

#### Scenario: Resolver con nota
- **WHEN** se elige Resolver con una nota no vacía
- **THEN** el panel solicita `RESOLVED`, actualiza el reporte y muestra una confirmación

#### Scenario: Incidencia resuelta
- **WHEN** una incidencia ya está resuelta
- **THEN** el panel presenta su estado y no ofrece una acción para reabrirla

### Requirement: Comunicación de estados de interfaz

El panel SHALL comunicar estados de carga, conexión con la API, errores y confirmaciones de las operaciones visibles.

#### Scenario: Carga de reportes
- **WHEN** se consultan reportes y resumen
- **THEN** el panel presenta un indicador de carga hasta que la consulta termina

#### Scenario: Error de API
- **WHEN** una solicitud falla
- **THEN** el panel presenta el mensaje de error y no comunica la acción como exitosa

#### Scenario: Confirmación de operación
- **WHEN** una carga, corrida o cambio de estado concluye exitosamente
- **THEN** el panel muestra una confirmación visible y permite cerrarla

### Requirement: Fecha inicial de la vista

El panel SHALL inicializar la fecha seleccionada con la fecha actual del navegador serializada en UTC.

#### Scenario: Abrir el panel
- **WHEN** una persona inicia la vista
- **THEN** la fecha inicial corresponde a los primeros diez caracteres de la fecha ISO UTC actual del navegador
