from collections.abc import Mapping
from dataclasses import dataclass

from app.models import DiscrepancyType, RecordSource
from app.schemas import ExplanationAssessment, SourceEvidenceGroup


MAX_EVIDENCE_ROWS_PER_SOURCE = 20


@dataclass(frozen=True)
class ExplanationGuidance:
    hypothesis: str
    recommendation: str


EXPLANATION_GUIDANCE: dict[DiscrepancyType, ExplanationGuidance] = {
    DiscrepancyType.MISSING_WALLET_RECORD: ExplanationGuidance(
        hypothesis="La fila puede no haberse cargado o la fuente puede no haberla informado; los datos disponibles no distinguen esas posibilidades.",
        recommendation="Verifica la carga y la completitud de la fuente wallet para esta fecha antes de cerrar la incidencia.",
    ),
    DiscrepancyType.MISSING_PROVIDER_RESULT: ExplanationGuidance(
        hypothesis="El resultado puede no haberse cargado todavía o puede no existir en la fuente; no hay evidencia para decidir cuál.",
        recommendation="Confirma con el proceso o responsable del proveedor si el lote de esta fecha está completo antes de cerrar la incidencia.",
    ),
    DiscrepancyType.MISSING_LEDGER_ENTRY: ExplanationGuidance(
        hypothesis="El asiento puede no haberse cargado todavía o puede faltar en el origen; la evidencia actual no establece la causa.",
        recommendation="Verifica la completitud del lote y el asiento correspondiente en ledger antes de cerrar la incidencia.",
    ),
    DiscrepancyType.DUPLICATE_WALLET_RECORD: ExplanationGuidance(
        hypothesis="Las filas repetidas podrían ser una duplicación de carga o eventos válidos separados; no se puede escoger una automáticamente.",
        recommendation="Compara los identificadores y atributos de cada fila wallet con la fuente autorizada; no elimines ni selecciones registros automáticamente.",
    ),
    DiscrepancyType.DUPLICATE_PROVIDER_RESULT: ExplanationGuidance(
        hypothesis="Los resultados repetidos podrían provenir de una duplicación de carga o de eventos distintos del proveedor.",
        recommendation="Verifica cada fila y su significado con el proveedor antes de decidir si la incidencia puede cerrarse.",
    ),
    DiscrepancyType.DUPLICATE_LEDGER_ENTRY: ExplanationGuidance(
        hypothesis="Los asientos repetidos podrían ser duplicados o movimientos legítimos separados; el conteo por sí solo no lo determina.",
        recommendation="Revisa cada asiento en ledger y confirma su validez antes de cerrar; no borres ni ajustes registros desde el agente.",
    ),
    DiscrepancyType.CHANNEL_MISMATCH: ExplanationGuidance(
        hypothesis="La diferencia puede deberse a valores de canal distintos entre fuentes o a cómo fueron cargados; la causa no está confirmada.",
        recommendation="Confirma el canal correcto con la evidencia fuente autorizada; no normalices ni cambies el canal automáticamente.",
    ),
    DiscrepancyType.AMOUNT_MISMATCH: ExplanationGuidance(
        hypothesis="Los importes almacenados difieren, pero la evidencia no determina si se debe a una carga, procesamiento o ajuste externo.",
        recommendation="Compara los importes de cada fuente con el comprobante o evidencia autorizada antes de solicitar una corrección.",
    ),
    DiscrepancyType.CURRENCY_MISMATCH: ExplanationGuidance(
        hypothesis="Los códigos de moneda actuales difieren; no se puede inferir una conversión ni cuál valor es correcto.",
        recommendation="Confirma la moneda de la operación con evidencia autorizada; no conviertas montos ni cambies códigos automáticamente.",
    ),
    DiscrepancyType.PROVIDER_NOT_SUCCESSFUL: ExplanationGuidance(
        hypothesis="El estado actual del proveedor no es SUCCESS; por sí solo no confirma el resultado final de liquidación.",
        recommendation="Verifica el estado exacto con el proveedor y evidencia de liquidación; trata PENDING como no concluyente.",
    ),
}


SOURCE_LABELS: dict[RecordSource, str] = {
    RecordSource.WALLET: "wallet",
    RecordSource.PROVIDER: "provider",
    RecordSource.LEDGER: "ledger",
}


def analyze_current_evidence(
    discrepancy_type: DiscrepancyType,
    evidence_by_source: Mapping[RecordSource, SourceEvidenceGroup],
) -> tuple[ExplanationAssessment, str, list[str], list[str], str]:
    if set(EXPLANATION_GUIDANCE) != set(DiscrepancyType):
        raise RuntimeError("Explanation guidance must cover every discrepancy type.")

    facts: list[str] = []
    for source in RecordSource:
        group = evidence_by_source[source]
        facts.append(
            f"Actualmente hay {group.current_record_count} registro(s) "
            f"{SOURCE_LABELS[source]} para esta referencia y fecha."
        )
        for record in group.records:
            status_text = f", estado {record.status}" if record.status else ""
            facts.append(
                f"Registro {record.record_id} ({SOURCE_LABELS[source]}): canal "
                f"{record.channel}, monto {record.amount_minor} {record.currency}"
                f"{status_text}."
            )
        if group.truncated:
            facts.append(
                f"La evidencia {SOURCE_LABELS[source]} está limitada a "
                f"{MAX_EVIDENCE_ROWS_PER_SOURCE} filas."
            )

    flattened = [
        record
        for source in RecordSource
        for record in evidence_by_source[source].records
    ]
    counts = {
        source: evidence_by_source[source].current_record_count
        for source in RecordSource
    }
    truncated = any(group.truncated for group in evidence_by_source.values())

    observed = False
    reason = ""
    if discrepancy_type in {
        DiscrepancyType.MISSING_WALLET_RECORD,
        DiscrepancyType.MISSING_PROVIDER_RESULT,
        DiscrepancyType.MISSING_LEDGER_ENTRY,
    }:
        source = {
            DiscrepancyType.MISSING_WALLET_RECORD: RecordSource.WALLET,
            DiscrepancyType.MISSING_PROVIDER_RESULT: RecordSource.PROVIDER,
            DiscrepancyType.MISSING_LEDGER_ENTRY: RecordSource.LEDGER,
        }[discrepancy_type]
        facts.append(
            f"En la corrida original se informó la ausencia de {SOURCE_LABELS[source]}; "
            f"la consulta actual encuentra {counts[source]} fila(s)."
        )
        reason = (
            "La base actual no demuestra que la fuente esté completa ni conserva "
            "un snapshot de las filas existentes al ejecutar la corrida."
        )
    elif discrepancy_type in {
        DiscrepancyType.DUPLICATE_WALLET_RECORD,
        DiscrepancyType.DUPLICATE_PROVIDER_RESULT,
        DiscrepancyType.DUPLICATE_LEDGER_ENTRY,
    }:
        source = {
            DiscrepancyType.DUPLICATE_WALLET_RECORD: RecordSource.WALLET,
            DiscrepancyType.DUPLICATE_PROVIDER_RESULT: RecordSource.PROVIDER,
            DiscrepancyType.DUPLICATE_LEDGER_ENTRY: RecordSource.LEDGER,
        }[discrepancy_type]
        observed = counts[source] > 1
        reason = (
            "Se observan varias filas actuales para esa fuente, pero eso no determina "
            "si son duplicados inválidos o eventos distintos."
            if observed
            else "La condición de duplicidad de la corrida original no se reproduce "
            "con las filas actuales."
        )
    elif discrepancy_type in {
        DiscrepancyType.CHANNEL_MISMATCH,
        DiscrepancyType.AMOUNT_MISMATCH,
        DiscrepancyType.CURRENCY_MISMATCH,
    }:
        attr_name, label = {
            DiscrepancyType.CHANNEL_MISMATCH: ("channel", "canal"),
            DiscrepancyType.AMOUNT_MISMATCH: ("amount_minor", "monto"),
            DiscrepancyType.CURRENCY_MISMATCH: ("currency", "moneda"),
        }[discrepancy_type]
        values = {getattr(record, attr_name) for record in flattened}
        present_sources = sum(counts[source] > 0 for source in RecordSource)
        observed = len(values) > 1 and present_sources > 1
        if values:
            facts.append(
                f"Valores actuales observados para {label}: "
                + ", ".join(str(value) for value in sorted(values))
                + "."
            )
        reason = (
            f"Los valores actuales de {label} difieren entre las filas consultadas; "
            "esto no determina la causa ni cuál valor debe prevalecer."
            if observed
            else f"La diferencia original de {label} no se reproduce con evidencia "
            "actual suficiente."
        )
    else:
        provider_records = evidence_by_source[RecordSource.PROVIDER].records
        unsuccessful = sorted(
            {
                record.status or ""
                for record in provider_records
                if record.status != "SUCCESS"
            }
        )
        observed = bool(unsuccessful)
        if unsuccessful:
            facts.append(
                "Estados actuales no exitosos del proveedor: "
                + ", ".join(status or "sin estado" for status in unsuccessful)
                + "."
            )
        reason = (
            "Se observa un estado actual del proveedor distinto de SUCCESS; "
            "esto no confirma liquidación ni resultado final."
            if observed
            else "La condición de estado no exitoso informada en la corrida original "
            "no se reproduce con los registros actuales del proveedor."
        )

    if truncated:
        observed = False
        reason = (
            "La consulta superó el límite de evidencia para alguna fuente; "
            "no se concluye a partir de una muestra truncada."
        )

    guidance = EXPLANATION_GUIDANCE[discrepancy_type]
    assessment = (
        ExplanationAssessment.OBSERVED
        if observed
        else ExplanationAssessment.INCONCLUSIVE
    )
    return (
        assessment,
        reason,
        facts,
        [guidance.hypothesis],
        guidance.recommendation,
    )
