# SDK Reference

## Supported Instrumentors

| Class path | Library |
|-----------|----------|
| `flow_forge_ai.instrumentation.openai_instr.OpenAIInstrumentor` | `openai` |
| `flow_forge_ai.instrumentation.ollama_instr.OllamaInstrumentor` | `ollama` |
| `flow_forge_ai.instrumentation.httpx_instr.HttpxInstrumentor` | `httpx` |
| `flow_forge_ai.instrumentation.requests_instr.RequestsInstrumentor` | `requests` |

Declare instrumentors in `config.toml`:

```toml
[[instrumentors]]
class_path = "flow_forge_ai.instrumentation.openai_instr.OpenAIInstrumentor"
```

---

## Supported Sinks

| Class path | Storage |
|-----------|----------|
| `flow_forge_ai.sinks.file_sink.FileSink` | JSONL file |
| `flow_forge_ai.sinks.console_sink.ConsoleSink` | stdout |
| `flow_forge_ai.sinks.memory_sink.MemorySink` | in-process list |
| `flow_forge_ai.sinks.database_sink.DatabaseSink` | pluggable handler (see below) |

`DatabaseSink` delegates persistence to a handler specified via `sinks.options.class_path`:

| Handler | Backend |
|---------|----------|
| `flow_forge_ai.sinks.handlers.jsonl_handler.JsonlHandler` | JSONL file |
| `flow_forge_ai.sinks.handlers.sqlite_handler.SQLiteHandler` | SQLite |
| `flow_forge_ai.sinks.handlers.postgres_handler.PostgresHandler` | PostgreSQL |
| `flow_forge_ai.sinks.handlers.mysql_handler.MySQLHandler` | MySQL |
| `flow_forge_ai.sinks.handlers.mongodb_handler.MongoDBHandler` | MongoDB |

---

## Runtime API

When `[runtime].enable = true`, the package starts a local HTTP listener that the UI connects to.

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/runs` | List all recorded runs |
| `GET` | `/api/steps?run_id=<id>` | List steps for a run |
| `POST` | `/api/runs/{run_id}/replay` | Start a replay |
| `GET` | `/api/runs/{run_id}/replay` | Get replay status |
| `DELETE` | `/api/runs/{run_id}/replay` | Stop a replay |

---

## `runtime.run()` — context manager

```python
from flow_forge_ai.runtime import runtime

with runtime.run(workflow="my-workflow") as run_id:
    ...
```

All instrumented library calls made inside the `with` block are associated with `run_id`.

---

## `@workflow` — decorator

```python
from flow_forge_ai.instrumentation.workflow import workflow

@workflow(workflow_id="my-pipeline")
def pipeline():
    ...
```

Equivalent to wrapping the function body in `with runtime.run(workflow=workflow_id)`.

### `@workflow.step`

Label individual logical steps within a workflow:

```python
@pipeline.step(step_id="fetch")
def fetch_data() -> list[str]:
    ...

@pipeline.step(step_id="process")
def process_data(items: list[str]) -> str:
    ...
```

---

## `@trace_tool` — decorator

```python
from flow_forge_ai.instrumentation.trace_tool import trace_tool

@trace_tool(version="v1", tool_id="knowledge_base_search")
def search_knowledge_base(query: str) -> str:
    ...
```

Emits `TOOL_START` and `TOOL_COMPLETED` events (or `TOOL_ERROR` on exception) in the same format as LLM tool calls, making tool invocations visible alongside model calls in the trace.

---

## Package Layout

```
core/src/flow_forge_ai/
├── runtime.py            # Runtime entry point (run context manager)
├── emitter.py            # Event emitter
├── context.py            # Run context
├── replay.py             # Replay manager
├── config/               # Config loading and models
├── instrumentation/      # Instrumentors + @workflow / @trace_tool decorators
├── sinks/                # Sink implementations and handlers
├── internal_logging/     # Internal logger
└── utils/                # Shared utilities
```
