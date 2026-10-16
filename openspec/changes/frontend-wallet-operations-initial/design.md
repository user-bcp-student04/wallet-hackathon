# Design

## Context

See `proposal.md` for motivation and `specs/frontend/operations-dashboard/spec.md` for the user-visible contract. The interface will consume API results for a selected date, expose explicit user actions, and keep the report view consistent with backend state.

## Goals / Non-Goals

**Goals:**
- Organize daily filters, summary metrics, run controls, source import, and report investigation in one operational view.
- Keep the API as the source of truth for report data and state changes.
- Provide clear feedback for loading, validation, failures, and successful operations.
- Keep channel-level metrics distinct from daily aggregate metrics.

**Non-Goals:**
- Provide global reconciliation history or a dedicated MCP explanation interface.
- Implement financial matching rules, persistence, authentication, or roles in the browser.
- Trigger runs, imports, or discrepancy changes automatically.
- Alter the specified UTC-derived initial date behavior.

## Decisions

### Use a single-page daily dashboard

Present date and channel filters, summary cards, a manual run form, a source import panel, and expandable reports in one view. A multi-route application was not selected because the MVP contains one primary operational workflow.

### Keep HTTP access in a typed API client

Centralize endpoint paths, request bodies, and response types in a client module. Surface non-success HTTP responses as errors that the view can display. Duplicated `fetch` handling inside each control was rejected because it would make error handling and data contracts inconsistent.

### Derive summary display from server responses

Use the daily summary when no channel is selected and the selected channel's report summary when a channel is selected. Do not recalculate financial or reconciliation metrics in the browser; this keeps the display consistent with backend counting rules.

### Refresh server state after mutations

After a successful import, run, or discrepancy update, reload reports and summary from the API. Use component state only for transient input, notices, and request progress. Treating optimistic local changes as authoritative was rejected because server validation and uniqueness rules remain decisive.

### Keep explanations and history outside this view

Limit the page to reports for the selected day and the currently specified manual investigation controls. A global history view and explanatory analysis panel would require separate user flows and are not included in this dashboard capability.

## Risks / Trade-offs

- [The initial date is based on browser UTC while backend demonstration data uses `America/Lima`] → Keep the requirement explicit and test date boundaries; any timezone change requires a separate product decision.
- [The view depends on API availability] → Show connection and error states and retain a manual refresh action.
- [JSON source data can be invalid or too large] → Validate JSON shape locally and surface backend validation errors; keep the allowed batch size visible.
- [No authentication or role model is defined] → Do not imply operator identity or permissions beyond the current local-use context.

## Migration Plan

No browser-data migration is required for the initial dashboard. Configure the frontend API base/proxy for the selected environment and build static assets for deployment. Rollback consists of restoring the prior frontend build; backend records are not modified by frontend rollback.
