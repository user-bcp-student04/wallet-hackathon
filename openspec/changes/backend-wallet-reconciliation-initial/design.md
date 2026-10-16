# Design

## Context

See `proposal.md` for motivation and `specs/backend/wallet-reconciliation-api/spec.md` for the behavioral contract. The service will need to ingest three normalized data sources, retain operational state, produce repeatable results, and offer a controlled interface for both the dashboard and MCP tools.

## Goals / Non-Goals

**Goals:**
- Keep API validation, persistence, classification, and reporting under one backend source of truth.
- Make date/channel uniqueness and discrepancy state transitions enforceable at the service and storage boundaries.
- Isolate deterministic explanation from state-changing investigation operations.
- Support reproducible local development without destructive startup behavior.

**Non-Goals:**
- Connect to live wallet, provider, or ledger systems.
- Add authentication, authorization, automated incident resolution, or scheduled reconciliation.
- Use an LLM as the source of matching decisions or verified root-cause claims.

## Decisions

### Use a layered HTTP service and persistence boundary

Implement the HTTP API as the service boundary, with request/response schemas, business logic, and data persistence separated. Use SQLAlchemy with SQLite for the local MVP because it supports persistent relational records and uniqueness constraints without requiring an external database service. A file-based store without relational constraints was rejected because it makes uniqueness and references harder to enforce.

### Make the comparison engine deterministic

Group source records by transaction reference and apply explicit comparison rules for missing/duplicate records, channel, amount, currency, and provider status. Persist each run and its discrepancies with a unique date/channel constraint. An asynchronous or probabilistic matcher was rejected for the MVP because identical inputs must produce explainable, repeatable results.

### Keep investigation and reconciliation as separate operations

Expose reconciliation creation separately from discrepancy updates. Require a note to resolve an incident and prevent a resolved state from being reopened. This preserves manual confirmation and avoids treating recommendations as completed operational work.

### Use read-only, bounded evidence for explanations

Build explanations from source evidence available at query time, limit each source to 20 rows, and report truncation or insufficient evidence as inconclusive. Do not persist explanation output as a state transition or label it as a snapshot of the original run. Unbounded reads and inferred root-cause assertions were rejected to limit exposure and avoid unsupported conclusions.

### Delegate MCP behavior to the HTTP API

Have MCP tools call the service API rather than access the database or duplicate matching logic. Keep run execution explicitly user-initiated; provide read-only tools for availability, reports, summaries, history, and explanations. Startup-triggered or scheduled execution is excluded.

### Seed local data without destructive resets

Provide optional synthetic development data for the five complete prior calendar days in `America/Lima`. Make the seed idempotent, skip it in production or when disabled, and never create runs as a side effect. Reset-on-start was rejected because it would destroy operational and demonstration records.

## Risks / Trade-offs

- [The MVP has no authentication or authorization] → Keep the service and MCP endpoint within an authorized local environment; do not expose it publicly without a separate security design.
- [A row cap may omit evidence needed to explain an incident] → Return an inconclusive evaluation whenever evidence is insufficient or truncated.
- [Current source data may differ from the data used for a prior run] → Include the query time and explicitly identify explanations as current evidence, not historical snapshots.
- [A deterministic recommendation can be mistaken for a verified cause] → Separate observed facts from unverified hypotheses and require a person to manage state changes.
- [SQLite is suitable for a local MVP but limits deployment options] → Keep persistence behind a data-access boundary so a future database migration can be designed separately.

## Migration Plan

For an initial deployment, create the schema and configure the local database path before starting the service. Enable synthetic seed only in development. No production-data migration is in scope. Rollback consists of stopping the service and restoring the database from a backup; the application must not delete database contents during startup.
