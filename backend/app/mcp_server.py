import json
import os
from datetime import date
from typing import Annotated
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from mcp.server.fastmcp import FastMCP
from pydantic import Field


API_BASE_URL = os.getenv("RECONCILIATION_API_URL", "http://127.0.0.1:8000").rstrip("/")
REQUEST_TIMEOUT_SECONDS = 10
mcp = FastMCP("Wallet Reconciliation")


class ApiError(RuntimeError):
    def __init__(self, status: int, detail: object) -> None:
        super().__init__(f"Reconciliation API returned HTTP {status}: {detail}")
        self.status = status


def _decode_json(body: bytes) -> object:
    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError("Reconciliation API returned invalid JSON.") from error


def _api_request(
    method: str, path: str, payload: dict[str, object] | None = None
) -> object:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = Request(
        f"{API_BASE_URL}{path}",
        data=body,
        method=method,
        headers={"Accept": "application/json", "Content-Type": "application/json"},
    )
    try:
        with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            return _decode_json(response.read())
    except HTTPError as error:
        detail = _decode_json(error.read())
        if isinstance(detail, dict):
            detail = detail.get("detail", detail)
        raise ApiError(error.code, detail) from error
    except URLError as error:
        raise RuntimeError(
            f"Cannot reach the reconciliation API at {API_BASE_URL}: {error.reason}"
        ) from error


def _validate_date(value: str) -> date:
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise ValueError("Use a valid operational date in YYYY-MM-DD format.") from error
    if parsed.isoformat() != value:
        raise ValueError("Use a valid operational date in YYYY-MM-DD format.")
    return parsed


def _as_object(value: object, context: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise RuntimeError(f"Unexpected {context} response from reconciliation API.")
    return value


def _as_array(value: object, context: str) -> list[object]:
    if not isinstance(value, list):
        raise RuntimeError(f"Unexpected {context} response from reconciliation API.")
    return value


def _report_for(date_value: str, channel: str) -> dict[str, object] | None:
    params = urlencode({"reconciliation_date": date_value, "channel": channel})
    reports = _as_array(
        _api_request("GET", f"/api/v1/reconciliations?{params}"),
        "reports",
    )
    for item in reports:
        report = _as_object(item, "report")
        if report.get("channel") == channel:
            return report
    return None


def _ensure_channel_has_data(date_value: str, channel: str) -> dict[str, object]:
    params = urlencode({"reconciliation_date": date_value})
    availability = _as_object(
        _api_request("GET", f"/api/v1/records/availability?{params}"),
        "availability",
    )
    channels = _as_array(availability.get("channels"), "availability channels")
    for item in channels:
        channel_data = _as_object(item, "channel availability")
        if channel_data.get("channel") == channel:
            total_records = channel_data.get("total_records")
            if not isinstance(total_records, int) or total_records <= 0:
                break
            return channel_data
    raise ValueError(
        f"No source data is available for {date_value} and channel {channel!r}; "
        "no reconciliation was created."
    )


@mcp.tool()
def list_available_reconciliation_data(
    reconciliation_date: Annotated[
        str,
        Field(description="Operational date to inspect, in YYYY-MM-DD format."),
    ],
) -> dict[str, object]:
    """List source record counts and existing runs for channels on an operational date."""
    parsed_date = _validate_date(reconciliation_date)
    params = urlencode({"reconciliation_date": parsed_date.isoformat()})
    return _as_object(
        _api_request("GET", f"/api/v1/records/availability?{params}"),
        "availability",
    )


@mcp.tool()
def run_reconciliation(
    reconciliation_date: Annotated[
        str,
        Field(description="Operational date with available data, in YYYY-MM-DD format."),
    ],
    channel: Annotated[
        str,
        Field(min_length=1, max_length=64, description="Exact available channel name."),
    ],
) -> dict[str, object]:
    """Run a reconciliation only when data exists; return an existing run instead of duplicating it."""
    parsed_date = _validate_date(reconciliation_date).isoformat()
    normalized_channel = channel.strip()
    if not normalized_channel:
        raise ValueError("Channel must not be blank.")

    _ensure_channel_has_data(parsed_date, normalized_channel)
    existing_report = _report_for(parsed_date, normalized_channel)
    if existing_report is not None:
        return {"created": False, "report": existing_report}

    request_body = {
        "reconciliation_date": parsed_date,
        "channel": normalized_channel,
    }
    try:
        created = _as_object(
            _api_request("POST", "/api/v1/reconciliations", request_body),
            "created run",
        )
    except ApiError as error:
        if error.status != 409:
            raise
        existing_report = _report_for(parsed_date, normalized_channel)
        if existing_report is None:
            raise
        return {"created": False, "report": existing_report}

    run_id = created.get("id")
    if not isinstance(run_id, int):
        raise RuntimeError("Reconciliation API did not return a valid run id.")
    report = _as_object(
        _api_request("GET", f"/api/v1/reconciliations/{run_id}"),
        "run report",
    )
    return {"created": True, "report": report}


@mcp.tool()
def get_reconciliation_report(
    reconciliation_date: Annotated[
        str,
        Field(description="Operational date, in YYYY-MM-DD format."),
    ],
    channel: Annotated[
        str,
        Field(min_length=1, max_length=64, description="Exact channel name."),
    ],
) -> dict[str, object]:
    """Retrieve the existing report for a date and channel without creating a run."""
    parsed_date = _validate_date(reconciliation_date).isoformat()
    normalized_channel = channel.strip()
    if not normalized_channel:
        raise ValueError("Channel must not be blank.")
    report = _report_for(parsed_date, normalized_channel)
    if report is None:
        raise ValueError(
            f"No reconciliation run exists for {parsed_date} and channel "
            f"{normalized_channel!r}."
        )
    return report


@mcp.tool()
def get_discrepancy_explanation(
    discrepancy_id: Annotated[
        int,
        Field(gt=0, description="Identifier of the discrepancy to analyze."),
    ],
) -> dict[str, object]:
    """Return a deterministic, read-only explanation based on current source evidence."""
    return _as_object(
        _api_request(
            "GET",
            f"/api/v1/discrepancies/{discrepancy_id}/explanation",
        ),
        "discrepancy explanation",
    )


@mcp.tool()
def get_daily_reconciliation_summary(
    reconciliation_date: Annotated[
        str,
        Field(description="Operational date, in YYYY-MM-DD format."),
    ],
) -> dict[str, object]:
    """Retrieve the daily transaction and resolved-incident summary."""
    parsed_date = _validate_date(reconciliation_date).isoformat()
    params = urlencode({"reconciliation_date": parsed_date})
    return _as_object(
        _api_request(
            "GET",
            f"/api/v1/reconciliations/daily-summary?{params}",
        ),
        "daily summary",
    )


@mcp.tool()
def list_reconciliation_history(
    start_date: Annotated[
        str | None,
        Field(
            description="Optional inclusive start date in YYYY-MM-DD format.",
        ),
    ] = None,
    end_date: Annotated[
        str | None,
        Field(
            description="Optional inclusive end date in YYYY-MM-DD format.",
        ),
    ] = None,
    channel: Annotated[
        str | None,
        Field(
            min_length=1,
            max_length=64,
            description="Optional exact channel filter.",
        ),
    ] = None,
    limit: Annotated[
        int,
        Field(ge=1, le=100, description="Page size, from 1 to 100."),
    ] = 50,
    offset: Annotated[
        int,
        Field(ge=0, description="Number of matching history items to skip."),
    ] = 0,
) -> dict[str, object]:
    """List existing reconciliations in reverse chronological order without changing data."""
    parsed_start = _validate_date(start_date).isoformat() if start_date else None
    parsed_end = _validate_date(end_date).isoformat() if end_date else None
    if parsed_start is not None and parsed_end is not None and parsed_start > parsed_end:
        raise ValueError("start_date must not be later than end_date.")
    normalized_channel = channel.strip() if channel is not None else None
    if channel is not None and not normalized_channel:
        raise ValueError("Channel must not be blank.")

    params = {
        key: value
        for key, value in {
            "start_date": parsed_start,
            "end_date": parsed_end,
            "channel": normalized_channel,
            "limit": str(limit),
            "offset": str(offset),
        }.items()
        if value is not None
    }
    return _as_object(
        _api_request(
            "GET",
            f"/api/v1/reconciliations/history?{urlencode(params)}",
        ),
        "reconciliation history",
    )


if __name__ == "__main__":
    mcp.run()
