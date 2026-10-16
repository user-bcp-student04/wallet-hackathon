from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
import logging
import os
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, HTTPException, Path, Query
from fastapi.openapi.utils import get_openapi
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.database import Base, SessionLocal, engine, get_session
from app.demo_data import seed_previous_demo_days
from app.explanations import MAX_EVIDENCE_ROWS_PER_SOURCE, analyze_current_evidence
from app.models import (
    Discrepancy,
    DiscrepancyType,
    InvestigationStatus,
    ReconciliationRun,
    RecordSource,
    SourceRecord,
)
from app.reconciliation import build_reconciliation, summarize
from app.schemas import (
    DiscrepancyResponse,
    DiscrepancyExplanation,
    DiscrepancyStatusUpdate,
    DailyReconciliationSummary,
    ExplanationAssessment,
    RecordAvailability,
    ReconciliationHistoryItem,
    ReconciliationHistoryPage,
    ReconciliationReport,
    ReconciliationRequest,
    ReconciliationRunResult,
    SourceEvidenceGroup,
    SourceRecordEvidence,
    SourceRecordBatch,
    SourceRecordLoadResult,
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    if demo_data_enabled():
        with SessionLocal() as session:
            current_date = datetime.now(ZoneInfo("America/Lima")).date()
            seeded_dates = seed_previous_demo_days(session, current_date)
            if seeded_dates:
                logger.info(
                    "Se cargaron datos de demostración para las fechas: %s",
                    ", ".join(item.isoformat() for item in seeded_dates),
                )
    yield


def demo_data_enabled() -> bool:
    app_environment = os.getenv("APP_ENV", "development").strip().casefold()
    if app_environment in {"production", "prod"}:
        return False

    configured_value = os.getenv("SEED_DEMO_DATA", "true").strip().casefold()
    if configured_value in {"1", "true", "yes", "on"}:
        return True
    if configured_value in {"0", "false", "no", "off"}:
        return False
    raise ValueError(
        "SEED_DEMO_DATA debe ser true/false, 1/0, yes/no u on/off."
    )


def create_app() -> FastAPI:
    app = FastAPI(
        title="API de conciliación de billetera",
        summary="Conciliación diaria de transacciones de billetera, proveedores y libro contable.",
        version="0.1.0",
        description=(
            "## Propósito\n"
            "API operativa del MVP de billetera para Perú. Permite cargar movimientos "
            "normalizados de la billetera, el proveedor y el libro contable (ledger), "
            "compararlos por fecha y canal, y administrar la investigación de los descalces.\n\n"
            "## Flujo recomendado\n"
            "1. Cargar los registros de cada fuente mediante `POST /api/v1/records/{source}`.\n"
            "2. Crear una corrida para una fecha y canal mediante `POST /api/v1/reconciliations`.\n"
            "3. Consultar el resultado, el resumen diario y los descalces encontrados.\n"
            "4. Actualizar el estado de investigación de cada descalce.\n\n"
            "## Reglas generales\n"
            "- Las fechas usan el formato `AAAA-MM-DD` y representan la fecha operativa de la transacción.\n"
            "- Los montos son enteros en unidades menores de la moneda: para PEN, céntimos. "
            "Por ejemplo, `2590` representa S/ 25.90.\n"
            "- La referencia de transacción debe ser la misma en las fuentes que representan la misma operación.\n"
            "- Solo se permite una corrida por combinación de fecha y canal; una repetición devuelve `409`.\n"
            "- El resumen distingue las transacciones resueltas de las incidencias resueltas.\n"
            "- La API no integra directamente con proveedores: recibe registros normalizados en lotes JSON."
        ),
        openapi_url="/openapi.json",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_tags=[
            {
                "name": "Estado del servicio",
                "description": "Verifica que el proceso de la API esté respondiendo.",
            },
            {
                "name": "Registros de origen",
                "description": (
                    "Consulta disponibilidad y carga movimientos normalizados de billetera, proveedor o libro contable. "
                    "Cada registro contiene referencia, fecha, canal, monto y moneda; el "
                    "resultado del proveedor también incluye un estado."
                ),
            },
            {
                "name": "Conciliaciones",
                "description": (
                    "Ejecuta comparaciones diarias y consulta reportes por fecha, canal o "
                    "identificador de corrida. Los totales distinguen transacciones conciliadas, "
                    "con descalces pendientes y con todos sus descalces resueltos."
                ),
            },
            {
                "name": "Descalces",
                "description": (
                    "Permite avanzar la investigación de un descalce y marcarlo como resuelto. "
                    "La resolución requiere una nota; en esta versión no se puede reabrir."
                ),
            },
        ],
        lifespan=lifespan,
    )

    @app.get(
        "/health",
        tags=["Estado del servicio"],
        summary="Comprobar disponibilidad de la API",
        description=(
            "Comprueba que la aplicación está activa. No verifica conectividad con terceros "
            "ni realiza una consulta de lectura o escritura en la base de datos."
        ),
        responses={200: {"description": "La API está activa y responde."}},
    )
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get(
        "/api/v1/records/availability",
        response_model=RecordAvailability,
        tags=["Registros de origen"],
        summary="Consultar disponibilidad de registros para una fecha",
        description=(
            "Devuelve por canal el número de registros cargados para cada fuente y "
            "si ya existe una corrida. No expone referencias ni datos de transacciones. "
            "Una fecha sin registros devuelve una lista de canales vacía."
        ),
    )
    def get_record_availability(
        session: Annotated[Session, Depends(get_session)],
        reconciliation_date: date = Query(
            description="Fecha operativa que se desea verificar, en formato AAAA-MM-DD."
        ),
    ) -> RecordAvailability:
        source_rows = session.execute(
            select(
                SourceRecord.channel,
                SourceRecord.source,
                func.count(SourceRecord.id),
            )
            .where(SourceRecord.transaction_date == reconciliation_date)
            .group_by(SourceRecord.channel, SourceRecord.source)
            .order_by(SourceRecord.channel, SourceRecord.source)
        ).all()
        runs = session.scalars(
            select(ReconciliationRun).where(
                ReconciliationRun.reconciliation_date == reconciliation_date
            )
        ).all()
        run_channels = {run.channel for run in runs}

        counts_by_channel: dict[str, dict[str, int]] = {}
        for channel_name, source_name, count in source_rows:
            counts_by_channel.setdefault(channel_name, {})[source_name] = count

        channels = []
        for channel_name, counts in counts_by_channel.items():
            source_counts = {
                source: counts.get(source.value, 0) for source in RecordSource
            }
            channels.append(
                {
                    "channel": channel_name,
                    "source_counts": source_counts,
                    "total_records": sum(source_counts.values()),
                    "reconciliation_exists": channel_name in run_channels,
                }
            )
        return RecordAvailability(
            reconciliation_date=reconciliation_date,
            channels=channels,
        )

    @app.post(
        "/api/v1/records/{source}",
        response_model=SourceRecordLoadResult,
        status_code=201,
        tags=["Registros de origen"],
        summary="Cargar un lote de registros de origen",
        description=(
            "Guarda entre 1 y 1,000 movimientos normalizados para la fuente indicada. "
            "Use `wallet` para la billetera, `provider` para resultados del proveedor y "
            "`ledger` para asientos del libro contable. Cada registro incluye referencia "
            "de transacción, fecha operativa, canal, monto positivo en unidades menores y "
            "código de moneda de tres letras.\n\n"
            "Para `provider`, `status` es obligatorio y acepta `SUCCESS` (operación exitosa), "
            "`FAILED` (operación fallida) o `PENDING` (resultado pendiente). Para `wallet` "
            "y `ledger`, no se debe enviar `status`. La carga agrega registros; no reemplaza "
            "ni deduplica cargas previas. Las filas duplicadas pueden ser señaladas por la conciliación."
        ),
        responses={
            201: {"description": "El lote se guardó. La respuesta informa fuente y cantidad de registros."},
            422: {"description": "El lote no cumple el formato, los límites o las reglas de la fuente seleccionada."},
        },
    )
    def load_source_records(
        source: Annotated[
            RecordSource,
            Path(
                description=(
                    "Sistema que produjo los movimientos: wallet (billetera), "
                    "provider (proveedor) o ledger (libro contable)."
                )
            ),
        ],
        batch: SourceRecordBatch,
        session: Annotated[Session, Depends(get_session)],
    ) -> SourceRecordLoadResult:
        if source == RecordSource.PROVIDER and any(
            record.status is None for record in batch.records
        ):
            raise HTTPException(
                status_code=422, detail="Los registros del proveedor requieren un estado de resultado."
            )
        if source != RecordSource.PROVIDER and any(
            record.status is not None for record in batch.records
        ):
            raise HTTPException(
                status_code=422, detail="Solo los registros del proveedor pueden incluir un estado de resultado."
            )

        session.add_all(
            [
                SourceRecord(
                    source=source.value,
                    transaction_reference=record.transaction_reference,
                    transaction_date=record.transaction_date,
                    channel=record.channel,
                    amount_minor=record.amount_minor,
                    currency=record.currency,
                    status=record.status.value if record.status else None,
                )
                for record in batch.records
            ]
        )
        session.commit()
        return SourceRecordLoadResult(source=source, loaded_count=len(batch.records))

    @app.post(
        "/api/v1/reconciliations",
        response_model=ReconciliationRunResult,
        status_code=201,
        tags=["Conciliaciones"],
        summary="Ejecutar una conciliación diaria",
        description=(
            "Compara los registros cargados para la fecha y canal indicados, agrupándolos "
            "por referencia de transacción. Detecta fuentes faltantes o duplicadas, "
            "diferencias de canal, monto y moneda, y resultados del proveedor distintos "
            "de `SUCCESS`. Una transacción sin descalces se cuenta como conciliada; una "
            "corrida ya existente para la misma fecha y canal no se repite."
        ),
        responses={
            201: {"description": "Corrida creada; incluye su identificador y resumen de totales."},
            409: {"description": "Ya existe una corrida para esa fecha y canal."},
        },
    )
    def create_reconciliation(
        request: ReconciliationRequest,
        session: Annotated[Session, Depends(get_session)],
    ) -> ReconciliationRunResult:
        existing = session.scalar(
            select(ReconciliationRun).where(
                ReconciliationRun.reconciliation_date == request.reconciliation_date,
                ReconciliationRun.channel == request.channel,
            )
        )
        if existing:
            raise HTTPException(
                status_code=409,
                detail="Ya existe una conciliación para esta fecha y canal.",
            )

        run = build_reconciliation(
            session, request.reconciliation_date, request.channel
        )
        try:
            session.commit()
        except IntegrityError as error:
            session.rollback()
            raise HTTPException(
                status_code=409,
                detail="Ya existe una conciliación para esta fecha y canal.",
            ) from error
        session.refresh(run)
        return ReconciliationRunResult(
            id=run.id,
            reconciliation_date=run.reconciliation_date,
            channel=run.channel,
            created_at=run.created_at,
            summary=summarize(run),
        )

    @app.get(
        "/api/v1/reconciliations",
        response_model=list[ReconciliationReport],
        tags=["Conciliaciones"],
        summary="Consultar reportes diarios de conciliación",
        description=(
            "Devuelve todas las corridas de la fecha indicada, ordenadas por canal. "
            "Puede limitar el resultado a un canal específico. Cada reporte contiene "
            "los totales de la corrida y el detalle de sus descalces. Si no hay corridas, "
            "devuelve una lista vacía."
        ),
        responses={
            200: {
                "description": (
                    "Lista de reportes para la fecha y los filtros solicitados; "
                    "puede ser una lista vacía."
                )
            }
        },
    )
    def list_reconciliations(
        session: Annotated[Session, Depends(get_session)],
        reconciliation_date: date = Query(
            description="Fecha operativa que se desea consultar, en formato AAAA-MM-DD.",
            examples=["2026-10-15"],
        ),
        channel: str | None = Query(
            default=None,
            min_length=1,
            max_length=64,
            description="Canal exacto por el que se filtrarán las corridas. Si se omite, se incluyen todos los canales.",
            examples=["qr"],
        ),
    ) -> list[ReconciliationReport]:
        statement = (
            select(ReconciliationRun)
            .options(selectinload(ReconciliationRun.discrepancies))
            .where(ReconciliationRun.reconciliation_date == reconciliation_date)
            .order_by(ReconciliationRun.channel)
        )
        if channel:
            statement = statement.where(ReconciliationRun.channel == channel)
        return [
            report_from_run(run)
            for run in session.scalars(statement).all()
        ]

    @app.get(
        "/api/v1/reconciliations/daily-summary",
        response_model=DailyReconciliationSummary,
        tags=["Conciliaciones"],
        summary="Consultar el resumen agregado del día",
        description=(
            "Suma los totales de todas las corridas de la fecha indicada, sin filtrar por "
            "canal. Devuelve la fecha, la lista de canales con corrida y el total de "
            "transacciones conciliadas, pendientes de investigación y resueltas. Si no "
            "existen corridas para ese día, los contadores son cero y la lista de canales "
            "está vacía."
        ),
        responses={
            200: {
                "description": (
                    "Resumen agregado de todas las corridas registradas para la fecha."
                )
            }
        },
    )
    def get_daily_summary(
        session: Annotated[Session, Depends(get_session)],
        reconciliation_date: date = Query(
            description="Fecha operativa del resumen que se desea consultar, en formato AAAA-MM-DD.",
            examples=["2026-10-15"],
        ),
    ) -> DailyReconciliationSummary:
        runs = session.scalars(
            select(ReconciliationRun)
            .options(selectinload(ReconciliationRun.discrepancies))
            .where(ReconciliationRun.reconciliation_date == reconciliation_date)
            .order_by(ReconciliationRun.channel)
        ).all()
        summaries = [summarize(run) for run in runs]
        return DailyReconciliationSummary(
            reconciliation_date=reconciliation_date,
            channels=[run.channel for run in runs],
            summary={
                "transaction_count": sum(item.transaction_count for item in summaries),
                "reconciled_count": sum(item.reconciled_count for item in summaries),
                "unreconciled_count": sum(item.unreconciled_count for item in summaries),
                "resolved_count": sum(item.resolved_count for item in summaries),
                "resolved_discrepancy_count": sum(
                    item.resolved_discrepancy_count for item in summaries
                ),
            },
        )

    @app.get(
        "/api/v1/reconciliations/history",
        response_model=ReconciliationHistoryPage,
        tags=["Conciliaciones"],
        summary="Consultar historial paginado de conciliaciones",
        description=(
            "Lista corridas existentes, de la más reciente a la más antigua, con su "
            "resumen y sin detalle de incidencias. Admite filtros opcionales por rango "
            "de fechas y canal, y paginación mediante limit y offset. Es una consulta "
            "de solo lectura."
        ),
    )
    def list_reconciliation_history(
        session: Annotated[Session, Depends(get_session)],
        start_date: date | None = Query(
            default=None,
            description="Fecha operativa inicial inclusiva, en formato AAAA-MM-DD.",
        ),
        end_date: date | None = Query(
            default=None,
            description="Fecha operativa final inclusiva, en formato AAAA-MM-DD.",
        ),
        channel: str | None = Query(
            default=None,
            min_length=1,
            max_length=64,
            description="Canal exacto opcional por el que se filtrarán las corridas.",
        ),
        limit: int = Query(
            default=50,
            ge=1,
            le=100,
            description="Cantidad máxima de elementos por página (1 a 100).",
        ),
        offset: int = Query(
            default=0,
            ge=0,
            description="Cantidad de elementos a omitir para recorrer las páginas.",
        ),
    ) -> ReconciliationHistoryPage:
        if start_date is not None and end_date is not None and start_date > end_date:
            raise HTTPException(
                status_code=422,
                detail="start_date no puede ser posterior a end_date.",
            )

        filters = []
        if start_date is not None:
            filters.append(ReconciliationRun.reconciliation_date >= start_date)
        if end_date is not None:
            filters.append(ReconciliationRun.reconciliation_date <= end_date)
        if channel is not None:
            filters.append(ReconciliationRun.channel == channel)

        total = session.scalar(
            select(func.count()).select_from(ReconciliationRun).where(*filters)
        )
        runs = session.scalars(
            select(ReconciliationRun)
            .options(selectinload(ReconciliationRun.discrepancies))
            .where(*filters)
            .order_by(
                ReconciliationRun.reconciliation_date.desc(),
                ReconciliationRun.created_at.desc(),
                ReconciliationRun.id.desc(),
            )
            .offset(offset)
            .limit(limit)
        ).all()
        return ReconciliationHistoryPage(
            total=total or 0,
            limit=limit,
            offset=offset,
            items=[
                ReconciliationHistoryItem(
                    run_id=run.id,
                    reconciliation_date=run.reconciliation_date,
                    channel=run.channel,
                    created_at=run.created_at,
                    summary=summarize(run),
                )
                for run in runs
            ],
        )

    @app.get(
        "/api/v1/reconciliations/{run_id}",
        response_model=ReconciliationReport,
        tags=["Conciliaciones"],
        summary="Consultar el detalle de una corrida",
        description=(
            "Devuelve una corrida específica con su fecha, canal, resumen y todos los "
            "descalces detectados. El estado y la nota de investigación más recientes "
            "se incluyen en cada descalce."
        ),
        responses={404: {"description": "No existe una corrida de conciliación con ese identificador."}},
    )
    def get_reconciliation(
        run_id: Annotated[
            int,
            Path(
                description="Identificador numérico de la corrida de conciliación.",
                gt=0,
                examples=[1],
            ),
        ],
        session: Annotated[Session, Depends(get_session)],
    ) -> ReconciliationReport:
        run = session.scalar(
            select(ReconciliationRun)
            .options(selectinload(ReconciliationRun.discrepancies))
            .where(ReconciliationRun.id == run_id)
        )
        if run is None:
            raise HTTPException(status_code=404, detail="No se encontró la conciliación solicitada.")
        return report_from_run(run)

    @app.get(
        "/api/v1/discrepancies/{discrepancy_id}/explanation",
        response_model=DiscrepancyExplanation,
        tags=["Descalces"],
        summary="Explicar un descalce usando evidencia fuente actual",
        description=(
            "Devuelve hechos observados, hipótesis no verificadas y una recomendación "
            "determinista para una incidencia. La evidencia se consulta en el momento "
            "de la solicitud, no es un snapshot de la corrida. Devuelve como máximo "
            f"{MAX_EVIDENCE_ROWS_PER_SOURCE} filas por fuente; si se supera el límite, "
            "la evaluación será no concluyente. Esta consulta no modifica datos ni estados."
        ),
        responses={404: {"description": "No existe el descalce solicitado."}},
    )
    def explain_discrepancy(
        discrepancy_id: Annotated[
            int,
            Path(
                description="Identificador numérico del descalce que se analizará.",
                gt=0,
            ),
        ],
        session: Annotated[Session, Depends(get_session)],
    ) -> DiscrepancyExplanation:
        discrepancy = session.scalar(
            select(Discrepancy)
            .options(selectinload(Discrepancy.run))
            .where(Discrepancy.id == discrepancy_id)
        )
        if discrepancy is None:
            raise HTTPException(status_code=404, detail="No se encontró el descalce solicitado.")

        run = discrepancy.run
        evidence_by_source: dict[RecordSource, SourceEvidenceGroup] = {}
        for source in RecordSource:
            filters = (
                SourceRecord.transaction_date == run.reconciliation_date,
                SourceRecord.transaction_reference
                == discrepancy.transaction_reference,
                SourceRecord.source == source.value,
            )
            record_count = session.scalar(
                select(func.count()).select_from(SourceRecord).where(*filters)
            )
            source_records = session.scalars(
                select(SourceRecord)
                .where(*filters)
                .order_by(SourceRecord.id)
                .limit(MAX_EVIDENCE_ROWS_PER_SOURCE)
            ).all()
            evidence_by_source[source] = SourceEvidenceGroup(
                source=source,
                current_record_count=record_count or 0,
                truncated=(record_count or 0) > MAX_EVIDENCE_ROWS_PER_SOURCE,
                records=[
                    SourceRecordEvidence(
                        record_id=record.id,
                        source=RecordSource(record.source),
                        transaction_date=record.transaction_date,
                        channel=record.channel,
                        amount_minor=record.amount_minor,
                        currency=record.currency,
                        status=record.status,
                        loaded_at=record.loaded_at,
                    )
                    for record in source_records
                ],
            )

        discrepancy_type = DiscrepancyType(discrepancy.discrepancy_type)
        (
            assessment,
            assessment_note,
            facts,
            hypotheses,
            recommendation,
        ) = analyze_current_evidence(discrepancy_type, evidence_by_source)
        return DiscrepancyExplanation(
            discrepancy=DiscrepancyResponse.model_validate(discrepancy),
            run_id=run.id,
            reconciliation_date=run.reconciliation_date,
            channel=run.channel,
            evidence_as_of=datetime.now(timezone.utc),
            assessment=assessment,
            assessment_note=assessment_note,
            facts=facts,
            hypotheses=hypotheses,
            recommendation=recommendation,
            evidence_by_source=list(evidence_by_source.values()),
        )

    @app.patch(
        "/api/v1/discrepancies/{discrepancy_id}",
        response_model=DiscrepancyResponse,
        tags=["Descalces"],
        summary="Actualizar la investigación de un descalce",
        description=(
            "Actualiza el estado de investigación a `OPEN` (abierto), `IN_PROGRESS` "
            "(en investigación) o `RESOLVED` (resuelto). Para resolverlo, envíe una "
            "nota que explique la investigación o el motivo de resolución. Si se "
            "envía una nota al cambiar a otro estado, se conserva como nota de investigación. "
            "En esta versión un descalce resuelto no se puede reabrir."
        ),
        responses={
            200: {"description": "Estado actualizado; devuelve el descalce con su nota y marcas de tiempo."},
            404: {"description": "No existe un descalce con ese identificador."},
            409: {"description": "No se puede reabrir un descalce que ya está resuelto."},
            422: {"description": "El estado no es válido o falta la nota obligatoria para resolver."},
        },
    )
    def update_discrepancy(
        discrepancy_id: Annotated[
            int,
            Path(
                description="Identificador numérico del descalce que se actualizará.",
                gt=0,
                examples=[1],
            ),
        ],
        update: DiscrepancyStatusUpdate,
        session: Annotated[Session, Depends(get_session)],
    ) -> Discrepancy:
        discrepancy = session.get(Discrepancy, discrepancy_id)
        if discrepancy is None:
            raise HTTPException(status_code=404, detail="No se encontró el descalce solicitado.")
        if (
            discrepancy.status == InvestigationStatus.RESOLVED.value
            and update.status != InvestigationStatus.RESOLVED
        ):
            raise HTTPException(
                status_code=409,
                detail="No se puede reabrir un descalce que ya está resuelto.",
            )
        discrepancy.status = update.status.value
        if update.investigation_note is not None:
            discrepancy.investigation_note = update.investigation_note
        session.commit()
        session.refresh(discrepancy)
        return discrepancy

    def localized_openapi():
        if app.openapi_schema:
            return app.openapi_schema

        schema = get_openapi(
            title=app.title,
            version=app.version,
            summary=app.summary,
            description=app.description,
            routes=app.routes,
            tags=app.openapi_tags,
        )
        component_schemas = schema.get("components", {}).get("schemas", {})
        localized_components = {
            "HTTPValidationError": (
                "Respuesta de validación",
                "Respuesta enviada cuando uno o más datos de la solicitud no cumplen las reglas del endpoint.",
            ),
            "ValidationError": (
                "Detalle del error de validación",
                "Indica qué dato de entrada no es válido y explica el motivo.",
            ),
            "DiscrepancyType": (
                "Tipo de descalce",
                "MISSING_WALLET_RECORD: falta en la billetera; MISSING_PROVIDER_RESULT: "
                "falta el resultado del proveedor; MISSING_LEDGER_ENTRY: falta el asiento "
                "contable; DUPLICATE_WALLET_RECORD: registro duplicado en billetera; "
                "DUPLICATE_PROVIDER_RESULT: resultado duplicado del proveedor; "
                "DUPLICATE_LEDGER_ENTRY: asiento duplicado; CHANNEL_MISMATCH: canal "
                "diferente; AMOUNT_MISMATCH: monto diferente; CURRENCY_MISMATCH: moneda "
                "diferente; PROVIDER_NOT_SUCCESSFUL: el proveedor no confirmó el éxito.",
            ),
            "InvestigationStatus": (
                "Estado de investigación",
                "OPEN significa abierto; IN_PROGRESS significa en investigación; "
                "RESOLVED significa resuelto.",
            ),
            "ProviderStatus": (
                "Resultado del proveedor",
                "SUCCESS significa exitoso; FAILED significa fallido; PENDING significa pendiente.",
            ),
            "RecordSource": (
                "Fuente de los registros",
                "wallet corresponde a la billetera; provider al proveedor de pagos; "
                "ledger al libro contable.",
            ),
            "ExplanationAssessment": (
                "Evaluación de evidencia",
                "OBSERVED indica que la condición se observa en los registros actuales; "
                "INCONCLUSIVE indica que la evidencia actual no permite confirmarla.",
            ),
            "SourceRecordEvidence": (
                "Registro fuente consultado",
                "Fila de la fuente consultada al momento del análisis; no necesariamente "
                "formó parte de la corrida original.",
            ),
            "SourceEvidenceGroup": (
                "Evidencia actual agrupada por fuente",
                "Conteo actual y hasta 20 filas de la referencia y fecha analizadas.",
            ),
            "DiscrepancyExplanation": (
                "Explicación de incidencia",
                "Resultado determinista de solo lectura con hechos, hipótesis no "
                "verificadas, recomendación y evidencia actual limitada.",
            ),
        }
        for component_name, (title, description) in localized_components.items():
            if component_name in component_schemas:
                component_schemas[component_name]["title"] = title
                component_schemas[component_name]["description"] = description

        field_titles = {
            "transaction_reference": "Referencia de transacción",
            "transaction_date": "Fecha de transacción",
            "channel": "Canal",
            "amount_minor": "Monto en unidades menores",
            "currency": "Moneda",
            "status": "Estado",
            "records": "Registros",
            "source": "Fuente",
            "loaded_count": "Cantidad de registros cargados",
            "id": "Identificador",
            "reconciliation_date": "Fecha de conciliación",
            "created_at": "Fecha de creación",
            "summary": "Resumen",
            "run_id": "Identificador de corrida",
            "discrepancies": "Descalces",
            "discrepancy_type": "Tipo de descalce",
            "details": "Detalle del descalce",
            "investigation_note": "Nota de investigación",
            "updated_at": "Fecha de actualización",
            "transaction_count": "Transacciones revisadas",
            "reconciled_count": "Transacciones conciliadas",
            "unreconciled_count": "Transacciones pendientes de investigación",
            "resolved_count": "Transacciones resueltas",
            "resolved_discrepancy_count": "Incidencias resueltas",
            "source_counts": "Registros por fuente",
            "record_id": "Identificador del registro",
            "current_record_count": "Cantidad actual de registros",
            "truncated": "Evidencia truncada",
            "evidence_as_of": "Evidencia consultada al momento",
            "evidence_temporality": "Temporalidad de la evidencia",
            "assessment": "Evaluación",
            "assessment_note": "Alcance de la evaluación",
            "facts": "Hechos observados",
            "hypotheses": "Hipótesis no verificadas",
            "recommendation": "Recomendación manual",
            "evidence_by_source": "Evidencia por fuente",
            "total_records": "Registros disponibles",
            "reconciliation_exists": "Ya existe corrida",
            "channels": "Canales",
            "detail": "Detalle del error",
            "loc": "Ubicación del error",
            "msg": "Motivo",
            "type": "Tipo de error",
            "input": "Dato recibido",
            "ctx": "Contexto de validación",
        }
        for component in component_schemas.values():
            for property_name, property_schema in component.get("properties", {}).items():
                if property_name in field_titles:
                    property_schema["title"] = field_titles[property_name]
                if property_name == "loc":
                    property_schema["description"] = (
                        "Ruta del campo inválido dentro de la solicitud."
                    )
                elif property_name == "msg":
                    property_schema["description"] = (
                        "Explicación de por qué el dato no es válido."
                    )
                elif property_name == "type":
                    property_schema["description"] = (
                        "Código técnico de la regla de validación incumplida."
                    )
                elif property_name == "input":
                    property_schema["description"] = (
                        "Valor recibido que produjo el error de validación."
                    )
                elif property_name == "ctx":
                    property_schema["description"] = (
                        "Datos adicionales asociados con el error de validación, si existen."
                    )
                elif property_name == "detail":
                    property_schema["description"] = (
                        "Lista de errores encontrados al validar los datos enviados."
                    )

        for path_item in schema.get("paths", {}).values():
            for operation in path_item.values():
                if not isinstance(operation, dict):
                    continue
                for status_code, response in operation.get("responses", {}).items():
                    if status_code == "422":
                        response["description"] = (
                            "La solicitud no cumple el formato, los límites o las "
                            "reglas de validación del endpoint."
                        )
                    elif response.get("description") == "Successful Response":
                        response["description"] = (
                            "Solicitud procesada correctamente. El cuerpo contiene "
                            "el resultado descrito en el modelo de respuesta."
                        )

        validation_error_example = {
            "dato_invalido": {
                "summary": "Un campo obligatorio no fue enviado",
                "value": {
                    "detail": [
                        {
                            "type": "missing",
                            "loc": ["body"],
                            "msg": "Falta un campo obligatorio.",
                            "input": {},
                        }
                    ]
                },
            }
        }
        def set_request_examples(
            path: str, method: str, examples: dict[str, dict[str, object]]
        ) -> None:
            request_body = schema["paths"][path][method].get("requestBody", {})
            media_type = request_body.get("content", {}).get("application/json")
            if media_type is not None:
                media_type["examples"] = examples

        def set_error_examples(
            path: str,
            method: str,
            status_code: str,
            examples: dict[str, dict[str, object]],
            *,
            includes_validation_errors: bool = False,
        ) -> None:
            response = schema["paths"][path][method]["responses"].get(status_code)
            if response is None:
                return
            error_schema: dict[str, object] = {
                "type": "object",
                "properties": {
                    "detail": {
                        "type": "string",
                        "title": "Detalle del error",
                    }
                },
                "required": ["detail"],
            }
            if includes_validation_errors:
                error_schema = {
                    "oneOf": [
                        {"$ref": "#/components/schemas/HTTPValidationError"},
                        error_schema,
                    ]
                }
            response["content"] = {
                "application/json": {
                    "schema": error_schema,
                    "examples": examples,
                }
            }

        def set_response_examples(
            path: str,
            method: str,
            status_code: str,
            examples: dict[str, dict[str, object]],
        ) -> None:
            response = schema["paths"][path][method]["responses"].get(status_code)
            if response is None:
                return
            media_type = response.get("content", {}).get("application/json")
            if media_type is not None:
                media_type["examples"] = examples

        for path, methods in schema["paths"].items():
            for method, operation in methods.items():
                if "422" in operation.get("responses", {}):
                    set_error_examples(
                        path,
                        method,
                        "422",
                        validation_error_example,
                        includes_validation_errors=True,
                    )

        reference_qr_ok = "demo-20261016-qr-001"
        reference_qr_amount = "demo-20261016-qr-002"
        discrepancy_example = {
            "id": 101,
            "transaction_reference": reference_qr_amount,
            "discrepancy_type": "AMOUNT_MISMATCH",
            "status": "OPEN",
            "details": "Wallet, provider, and ledger amounts do not match.",
            "investigation_note": None,
            "created_at": "2026-10-16T14:00:00Z",
            "updated_at": "2026-10-16T14:00:00Z",
        }
        summary_qr = {
            "transaction_count": 3,
            "reconciled_count": 1,
            "unreconciled_count": 2,
            "resolved_count": 0,
            "resolved_discrepancy_count": 0,
        }
        report_qr = {
            "run_id": 11,
            "reconciliation_date": "2026-10-16",
            "channel": "qr",
            "summary": summary_qr,
            "discrepancies": [
                discrepancy_example,
                {
                    **discrepancy_example,
                    "id": 102,
                    "transaction_reference": "demo-20261016-qr-003",
                    "discrepancy_type": "MISSING_PROVIDER_RESULT",
                    "details": "No provider record was found for this transaction.",
                },
            ],
        }

        set_response_examples(
            "/health",
            "get",
            "200",
            {
                "servicio_activo": {
                    "summary": "La API responde",
                    "value": {"status": "ok"},
                }
            },
        )
        source_examples = {
            "billetera": {
                "summary": "Registro de billetera",
                "description": "El campo status se omite para wallet.",
                "value": {
                    "records": [
                        {
                            "transaction_reference": reference_qr_ok,
                            "transaction_date": "2026-10-16",
                            "channel": "qr",
                            "amount_minor": 2500,
                            "currency": "PEN",
                        }
                    ]
                },
            },
            "proveedor": {
                "summary": "Resultado exitoso del proveedor",
                "description": "El campo status es obligatorio para provider.",
                "value": {
                    "records": [
                        {
                            "transaction_reference": reference_qr_ok,
                            "transaction_date": "2026-10-16",
                            "channel": "qr",
                            "amount_minor": 2500,
                            "currency": "PEN",
                            "status": "SUCCESS",
                        }
                    ]
                },
            },
            "libro_contable": {
                "summary": "Asiento del libro contable",
                "description": "El campo status se omite para ledger.",
                "value": {
                    "records": [
                        {
                            "transaction_reference": reference_qr_ok,
                            "transaction_date": "2026-10-16",
                            "channel": "qr",
                            "amount_minor": 2500,
                            "currency": "PEN",
                        }
                    ]
                },
            },
        }
        set_request_examples("/api/v1/records/{source}", "post", source_examples)
        set_response_examples(
            "/api/v1/records/{source}",
            "post",
            "201",
            {
                "lote_guardado": {
                    "summary": "Se guardó un registro",
                    "value": {"source": "wallet", "loaded_count": 1},
                }
            },
        )
        set_error_examples(
            "/api/v1/records/{source}",
            "post",
            "422",
            {
                **validation_error_example,
                "estado_de_proveedor_obligatorio": {
                    "summary": "Falta el resultado del proveedor",
                    "value": {
                        "detail": "Los registros del proveedor requieren un estado de resultado."
                    },
                },
                "estado_no_permitido": {
                    "summary": "Wallet o ledger incluyen un estado",
                    "value": {
                        "detail": "Solo los registros del proveedor pueden incluir un estado de resultado."
                    },
                },
            },
            includes_validation_errors=True,
        )

        set_request_examples(
            "/api/v1/reconciliations",
            "post",
            {
                "crear_corrida_qr": {
                    "summary": "Conciliar el canal QR",
                    "value": {"reconciliation_date": "2026-10-16", "channel": "qr"},
                },
                "crear_corrida_p2p": {
                    "summary": "Conciliar el canal P2P",
                    "value": {"reconciliation_date": "2026-10-16", "channel": "p2p"},
                },
            },
        )
        set_response_examples(
            "/api/v1/reconciliations",
            "post",
            "201",
            {
                "corrida_creada": {
                    "summary": "Corrida creada con una transacción conciliada y dos pendientes",
                    "value": {
                        "id": 11,
                        "reconciliation_date": "2026-10-16",
                        "channel": "qr",
                        "created_at": "2026-10-16T14:00:00Z",
                        "summary": summary_qr,
                    },
                }
            },
        )
        set_error_examples(
            "/api/v1/reconciliations",
            "post",
            "409",
            {
                "corrida_duplicada": {
                    "summary": "Ya existe una corrida para ese día y canal",
                    "value": {"detail": "Ya existe una conciliación para esta fecha y canal."},
                }
            },
        )

        set_response_examples(
            "/api/v1/reconciliations",
            "get",
            "200",
            {
                "reportes_del_dia": {
                    "summary": "Corridas QR y P2P para la fecha",
                    "value": [
                        report_qr,
                        {
                            "run_id": 12,
                            "reconciliation_date": "2026-10-16",
                            "channel": "p2p",
                            "summary": {
                                "transaction_count": 2,
                                "reconciled_count": 1,
                                "unreconciled_count": 1,
                                "resolved_count": 0,
                                "resolved_discrepancy_count": 0,
                            },
                            "discrepancies": [
                                {
                                    **discrepancy_example,
                                    "id": 103,
                                    "transaction_reference": "demo-20261016-p2p-002",
                                    "discrepancy_type": "PROVIDER_NOT_SUCCESSFUL",
                                    "details": "Provider result status is not SUCCESS: PENDING.",
                                }
                            ],
                        },
                    ],
                },
                "sin_corridas": {
                    "summary": "No hay corridas para la fecha",
                    "value": [],
                },
            },
        )
        set_response_examples(
            "/api/v1/reconciliations/daily-summary",
            "get",
            "200",
            {
                "resumen_con_corridas": {
                    "summary": "Resumen del día con corridas QR y P2P",
                    "value": {
                        "reconciliation_date": "2026-10-16",
                        "channels": ["p2p", "qr"],
                        "summary": {
                            "transaction_count": 5,
                            "reconciled_count": 2,
                            "unreconciled_count": 3,
                            "resolved_count": 0,
                            "resolved_discrepancy_count": 0,
                        },
                    },
                },
                "resumen_sin_corridas": {
                    "summary": "Resumen de una fecha sin corridas",
                    "value": {
                        "reconciliation_date": "2026-10-15",
                        "channels": [],
                        "summary": {
                            "transaction_count": 0,
                            "reconciled_count": 0,
                            "unreconciled_count": 0,
                            "resolved_count": 0,
                            "resolved_discrepancy_count": 0,
                        },
                    },
                },
            },
        )
        set_response_examples(
            "/api/v1/reconciliations/{run_id}",
            "get",
            "200",
            {
                "detalle_corrida": {
                    "summary": "Detalle de la corrida QR",
                    "value": report_qr,
                }
            },
        )
        set_error_examples(
            "/api/v1/reconciliations/{run_id}",
            "get",
            "404",
            {
                "corrida_inexistente": {
                    "summary": "El identificador no existe",
                    "value": {"detail": "No se encontró la conciliación solicitada."},
                }
            },
        )

        set_request_examples(
            "/api/v1/discrepancies/{discrepancy_id}",
            "patch",
            {
                "iniciar_investigacion": {
                    "summary": "Marcar descalce en investigación",
                    "value": {
                        "status": "IN_PROGRESS",
                        "investigation_note": "Se solicitó confirmación al proveedor.",
                    },
                },
                "resolver_descalce": {
                    "summary": "Resolver con una nota obligatoria",
                    "value": {
                        "status": "RESOLVED",
                        "investigation_note": "El proveedor confirmó la liquidación.",
                    },
                },
            },
        )
        set_response_examples(
            "/api/v1/discrepancies/{discrepancy_id}",
            "patch",
            "200",
            {
                "descalce_actualizado": {
                    "summary": "El descalce quedó resuelto",
                    "value": {
                        **discrepancy_example,
                        "status": "RESOLVED",
                        "investigation_note": "El proveedor confirmó la liquidación.",
                        "updated_at": "2026-10-16T15:00:00Z",
                    },
                }
            },
        )
        set_error_examples(
            "/api/v1/discrepancies/{discrepancy_id}",
            "patch",
            "404",
            {
                "descalce_inexistente": {
                    "summary": "El identificador no existe",
                    "value": {"detail": "No se encontró el descalce solicitado."},
                }
            },
        )
        set_error_examples(
            "/api/v1/discrepancies/{discrepancy_id}",
            "patch",
            "409",
            {
                "no_reabrir": {
                    "summary": "No se puede reabrir un descalce resuelto",
                    "value": {"detail": "No se puede reabrir un descalce que ya está resuelto."},
                }
            },
        )

        app.openapi_schema = schema
        return schema

    app.openapi = localized_openapi
    return app


def report_from_run(run: ReconciliationRun) -> ReconciliationReport:
    return ReconciliationReport(
        run_id=run.id,
        reconciliation_date=run.reconciliation_date,
        channel=run.channel,
        summary=summarize(run),
        discrepancies=[
            DiscrepancyResponse.model_validate(discrepancy)
            for discrepancy in sorted(run.discrepancies, key=lambda item: item.id)
        ],
    )


app = create_app()
