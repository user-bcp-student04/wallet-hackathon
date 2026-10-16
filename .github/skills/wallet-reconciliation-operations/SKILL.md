---
name: wallet-reconciliation-operations
description: "Use when a user manually requests available data, a reconciliation run, or a report for operational dates using the wallet-reconciliation MCP tools."
---

# Wallet Reconciliation Operations

Use the local `wallet-reconciliation` MCP tools to inspect and execute the
deterministic backend workflow. This skill documents a manual runbook; it does
not schedule or start runs by itself.

## Required inputs

- One or more operational dates in `YYYY-MM-DD` format. Resolve relative dates
  such as “yesterday” using `America/Lima`.
- Optional channel names. If omitted, inspect availability and use the channels
  returned for each date.
- A clear user request to execute before calling the run tool. Inspection and
  report requests remain read-only.

## Procedure

1. Call `list_available_reconciliation_data` for every requested date.
2. Confirm each requested date/channel has at least one source record. If a
   date or channel is absent, report that no run was created for it.
3. Check whether the availability result or report indicates an existing run.
   Existing runs are returned instead of being recreated; the backend rejects
   duplicate date/channel runs.
4. For a user-requested execution with available records, call
   `run_reconciliation` for each date/channel pair.
5. Retrieve additional detail with `get_reconciliation_report` when needed.
   Use `get_daily_reconciliation_summary` for the date-wide aggregate.
6. Report run ID and whether it was newly created or already existed. Show
   transaction counts separately from discrepancy counts, including resolved
   transactions and resolved discrepancies as distinct metrics.
7. For a request to list previous runs, call `list_reconciliation_history`
   with optional inclusive date filters and channel. Continue through pages
   using `offset + limit` until all items indicated by `total` are retrieved.
   This tool is read-only and returns summaries; request individual reports
   only if discrepancy-level detail is needed.
8. For a request to explain an incident, call `get_discrepancy_explanation` for
   the incident ID. Report the assessment, observed facts, unverified
   hypotheses, current source evidence and suggested manual verification
   separately. The evidence is current at query time, not a snapshot of the
   original run; at most 20 rows per source are returned. A truncated or
   insufficient result is inconclusive.
   Use the tool through Copilot only in an environment authorized to process
   this transaction evidence; tool results may be included in the selected
   model's context.
9. Surface API/network errors explicitly. Do not retry a failed or duplicate
   operation blindly, claim that a run succeeded without a returned report, or
   represent incomplete data as a complete financial reconciliation.

## Safety boundaries

- Demo records are synthetic and must never be represented as real financial
  data.
- The MCP server only reads availability/reports and requests a reconciliation
  through the existing backend API.
- `get_discrepancy_explanation` is read-only. Its deterministic recommendations
  do not update records, statuses or notes; an analyst must verify the evidence
  and manage any state change separately.
- Do not upload or modify source data, change investigation states, or write to
  wallet/provider/ledger records through MCP.
- No background scheduler is configured by this skill.
