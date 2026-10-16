from datetime import date, datetime
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.models import DiscrepancyType, InvestigationStatus, RecordSource


Reference = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)]
Channel = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]


class ProviderStatus(StrEnum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    PENDING = "PENDING"


class SourceRecordInput(BaseModel):
    transaction_reference: Reference = Field(
        description=(
            "Referencia única de la transacción, compartida por las fuentes que "
            "representan la misma operación. Se utiliza para cruzar los registros."
        ),
        examples=["tx-20261015-0001"],
    )
    transaction_date: date = Field(
        description="Fecha operativa de la transacción. Debe coincidir con la fecha de la corrida que la conciliará.",
        examples=["2026-10-15"],
    )
    channel: Channel = Field(
        description="Canal de pago o del proveedor, por ejemplo qr o p2p.",
        examples=["qr"],
    )
    amount_minor: int = Field(
        gt=0,
        description="Monto positivo expresado como entero en unidades menores. Para PEN se usan céntimos: 2590 equivale a S/ 25.90.",
        examples=[2590],
    )
    currency: str = Field(
        pattern=r"^[A-Z]{3}$",
        description="Código de moneda de tres letras mayúsculas según ISO 4217, por ejemplo PEN.",
        examples=["PEN"],
    )
    status: ProviderStatus | None = Field(
        default=None,
        description=(
            "Resultado informado por el proveedor: SUCCESS (exitoso), FAILED (fallido) "
            "o PENDING (pendiente). Es obligatorio para la fuente provider y debe "
            "omitirse para wallet y ledger."
        ),
        examples=["SUCCESS"],
    )

    model_config = ConfigDict(title="Registro de origen")


class SourceRecordBatch(BaseModel):
    records: list[SourceRecordInput] = Field(
        min_length=1,
        max_length=1000,
        description="Lote de entre 1 y 1,000 registros normalizados de la fuente indicada en la ruta.",
    )

    model_config = ConfigDict(
        title="Lote de registros de origen",
        json_schema_extra={
            "examples": [
                {
                    "records": [
                        {
                            "transaction_reference": "tx-20261015-0001",
                            "transaction_date": "2026-10-15",
                            "channel": "qr",
                            "amount_minor": 2590,
                            "currency": "PEN",
                            "status": "SUCCESS",
                        }
                    ]
                }
            ]
        }
    )


class SourceRecordLoadResult(BaseModel):
    source: RecordSource = Field(
        description=(
            "Sistema de origen de los registros: wallet (billetera), provider "
            "(proveedor de pagos) o ledger (libro contable)."
        )
    )
    loaded_count: int = Field(description="Cantidad de registros guardados correctamente.")

    model_config = ConfigDict(title="Resultado de carga de registros")


class ChannelRecordAvailability(BaseModel):
    channel: str = Field(description="Canal con registros de origen disponibles.")
    source_counts: dict[RecordSource, int] = Field(
        description="Cantidad de registros disponibles por fuente."
    )
    total_records: int = Field(description="Cantidad total de registros de origen.")
    reconciliation_exists: bool = Field(
        description="Indica si ya existe una corrida para esta fecha y canal."
    )


class RecordAvailability(BaseModel):
    reconciliation_date: date = Field(description="Fecha operativa consultada.")
    channels: list[ChannelRecordAvailability] = Field(
        description="Canales que tienen al menos un registro disponible."
    )


class ReconciliationRequest(BaseModel):
    reconciliation_date: date = Field(
        description="Fecha operativa cuyos registros se compararán, en formato AAAA-MM-DD.",
        examples=["2026-10-15"],
    )
    channel: Channel = Field(
        description="Canal exacto que se incluirá en esta corrida, por ejemplo qr o p2p.",
        examples=["qr"],
    )

    model_config = ConfigDict(title="Solicitud de conciliación")


class ReconciliationRunResult(BaseModel):
    id: int = Field(description="Identificador asignado a la corrida creada.")
    reconciliation_date: date = Field(description="Fecha operativa conciliada.")
    channel: str = Field(description="Canal incluido en esta corrida.")
    created_at: datetime = Field(description="Fecha y hora UTC en que se creó la corrida.")
    summary: "ReconciliationSummary" = Field(description="Totales de transacciones de esta corrida.")

    model_config = ConfigDict(
        from_attributes=True,
        title="Resultado de la corrida de conciliación",
    )


class DiscrepancyResponse(BaseModel):
    id: int = Field(description="Identificador del descalce; se utiliza para actualizarlo.")
    transaction_reference: str = Field(description="Referencia de la transacción afectada.")
    discrepancy_type: DiscrepancyType = Field(
        description=(
            "Tipo detectado: registro faltante, registro duplicado, diferencia de canal, "
            "monto o moneda, o resultado del proveedor no exitoso."
        )
    )
    status: InvestigationStatus = Field(
        description="Estado actual: OPEN (abierto), IN_PROGRESS (en investigación) o RESOLVED (resuelto)."
    )
    details: str = Field(description="Explicación del descalce detectado durante la comparación.")
    investigation_note: str | None = Field(
        description="Nota registrada por operaciones durante la investigación o resolución."
    )
    created_at: datetime = Field(description="Fecha y hora UTC en que se detectó el descalce.")
    updated_at: datetime = Field(description="Fecha y hora UTC de la última actualización del descalce.")

    model_config = ConfigDict(from_attributes=True, title="Descalce")


class ExplanationAssessment(StrEnum):
    OBSERVED = "OBSERVED"
    INCONCLUSIVE = "INCONCLUSIVE"


class SourceRecordEvidence(BaseModel):
    record_id: int = Field(description="Identificador del registro fuente.")
    source: RecordSource = Field(description="Fuente que informó el registro.")
    transaction_date: date = Field(description="Fecha operativa del registro.")
    channel: str = Field(description="Canal informado por la fuente.")
    amount_minor: int = Field(description="Monto en unidades menores.")
    currency: str = Field(description="Moneda informada por la fuente.")
    status: str | None = Field(description="Estado informado por el proveedor, si aplica.")
    loaded_at: datetime = Field(description="Momento en que el registro fue cargado al sistema.")

    model_config = ConfigDict(title="Evidencia de registro fuente")


class SourceEvidenceGroup(BaseModel):
    source: RecordSource = Field(description="Fuente de la evidencia.")
    current_record_count: int = Field(description="Cantidad actual de filas para la referencia y fecha.")
    truncated: bool = Field(description="Indica si se omitieron filas por alcanzar el límite de evidencia.")
    records: list[SourceRecordEvidence] = Field(description="Filas actuales de esta fuente, hasta el límite indicado.")

    model_config = ConfigDict(title="Grupo de evidencia por fuente")


class DiscrepancyExplanation(BaseModel):
    discrepancy: DiscrepancyResponse = Field(description="Incidencia que se está analizando.")
    run_id: int = Field(description="Corrida original en la que se detectó la incidencia.")
    reconciliation_date: date = Field(description="Fecha operativa de la corrida.")
    channel: str = Field(description="Canal de la corrida original.")
    evidence_as_of: datetime = Field(
        description="Momento de consulta; la evidencia refleja el estado actual y no un snapshot histórico."
    )
    evidence_temporality: str = Field(
        default="CURRENT_AT_QUERY",
        description="La evidencia consultada puede incluir cargas posteriores a la corrida original.",
    )
    assessment: ExplanationAssessment = Field(
        description="OBSERVED confirma la condición en filas actuales; INCONCLUSIVE indica evidencia insuficiente o no concluyente."
    )
    assessment_note: str = Field(description="Alcance y límites de la evaluación.")
    facts: list[str] = Field(description="Hechos calculados directamente a partir de la incidencia y las filas actuales.")
    hypotheses: list[str] = Field(description="Posibles explicaciones no verificadas; no son causas confirmadas.")
    recommendation: str = Field(description="Siguiente acción manual sugerida; no modifica datos ni estados.")
    evidence_by_source: list[SourceEvidenceGroup] = Field(description="Evidencia acotada por fuente.")

    model_config = ConfigDict(title="Análisis explicable de incidencia")


class DiscrepancyStatusUpdate(BaseModel):
    status: InvestigationStatus = Field(
        description=(
            "Nuevo estado de investigación: OPEN (abierto), IN_PROGRESS (en investigación) "
            "o RESOLVED (resuelto). Un descalce resuelto no se puede reabrir."
        )
    )
    investigation_note: str | None = Field(
        default=None,
        max_length=512,
        description="Nota de investigación, de hasta 512 caracteres. Es obligatoria cuando el estado es RESOLVED.",
        examples=["Se verificó el archivo de liquidación del proveedor."],
    )

    @model_validator(mode="after")
    def resolved_requires_note(self) -> "DiscrepancyStatusUpdate":
        if self.status == InvestigationStatus.RESOLVED and not self.investigation_note:
            raise ValueError("La nota de investigación es obligatoria para resolver un descalce.")
        return self

    model_config = ConfigDict(title="Actualización de investigación de descalce")


class ReconciliationSummary(BaseModel):
    transaction_count: int = Field(description="Cantidad de referencias de transacción distintas incluidas en la corrida.")
    reconciled_count: int = Field(description="Transacciones sin ningún descalce detectado.")
    unreconciled_count: int = Field(description="Transacciones con al menos un descalce que aún no está resuelto.")
    resolved_count: int = Field(description="Transacciones con descalces y con todos sus descalces resueltos.")
    resolved_discrepancy_count: int = Field(
        description="Cantidad de incidencias individuales cuyo estado actual es RESOLVED."
    )

    model_config = ConfigDict(title="Resumen de conciliación")


class DailyReconciliationSummary(BaseModel):
    reconciliation_date: date = Field(description="Fecha operativa del resumen diario.")
    channels: list[str] = Field(description="Canales que tienen una corrida creada para la fecha.")
    summary: ReconciliationSummary = Field(description="Totales agregados de todas las corridas de la fecha.")

    model_config = ConfigDict(title="Resumen diario agregado")


class ReconciliationReport(BaseModel):
    run_id: int = Field(description="Identificador de la corrida.")
    reconciliation_date: date = Field(description="Fecha operativa conciliada.")
    channel: str = Field(description="Canal incluido en la corrida.")
    summary: ReconciliationSummary = Field(description="Totales de transacciones de esta corrida.")
    discrepancies: list[DiscrepancyResponse] = Field(
        description="Lista de descalces encontrados y su estado actual de investigación."
    )

    model_config = ConfigDict(title="Reporte de conciliación")


class ReconciliationHistoryItem(BaseModel):
    run_id: int = Field(description="Identificador de la corrida.")
    reconciliation_date: date = Field(description="Fecha operativa conciliada.")
    channel: str = Field(description="Canal incluido en la corrida.")
    created_at: datetime = Field(description="Fecha y hora UTC de creación de la corrida.")
    summary: ReconciliationSummary = Field(description="Totales de la corrida.")

    model_config = ConfigDict(title="Elemento del historial de conciliaciones")


class ReconciliationHistoryPage(BaseModel):
    total: int = Field(description="Cantidad total de corridas que cumplen los filtros.")
    limit: int = Field(description="Máximo de elementos devueltos por página.")
    offset: int = Field(description="Índice del primer elemento de esta página.")
    items: list[ReconciliationHistoryItem] = Field(
        description="Corridas ordenadas de la más reciente a la más antigua."
    )

    model_config = ConfigDict(title="Página del historial de conciliaciones")
