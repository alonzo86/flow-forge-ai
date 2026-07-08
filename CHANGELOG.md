# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added
- Core: Added Python logging instrumentation via `flow_forge_ai.instrumentation.logging_instr.LoggingInstrumentor`.
- Core: Added new event type `log.record` to represent structured logging records.
- Core: Added `flow_forge_ai.instrumentation.langchain_instr.LangChainInstrumentor` for LangChain runnable tracing.
- Core: Added `core/examples/05_langchain_runnable_pipeline` to demonstrate LangChain runnable tracing with a JSONL sink.
- UI: Added run export endpoint `GET /api/runs/{run_id}/export` returning run metadata, steps, and flattened events.
- UI: Added run filtering and pagination support on `GET /api/runs` with `search`, `run_id`, `workflow_id`, `limit`, `offset`, `started_after`, and `started_before` query parameters.
- UI: Added run filtering controls and export action in the main UI template.
- Tests: Added core tests for logging, LangChain instrumentation, and the new LangChain example plus UI tests for filtering, pagination, and export routes.

### Changed
- UI: Fixed client-side step loading path to call `/api/steps`.
- Documentation: Updated root, core, and UI READMEs and SDK docs to reflect new instrumentation and API capabilities.
