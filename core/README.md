# flow-forge-ai

Core runtime, instrumentation, and storage package for Flow Forge AI.

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white)](#installation)
[![Tests: pytest](https://img.shields.io/badge/tests-pytest-0A9EDC?logo=pytest&logoColor=white)](#development)
[![Coverage: pytest-cov](https://img.shields.io/badge/coverage-pytest--cov-00A98F)](#development)
[![Type Checking: pyright](https://img.shields.io/badge/type%20checking-pyright-2C5BB4)](#development)

## What It Does

- Wraps workflow code with a lightweight run context (context manager or decorator)
- Auto-instruments LLM and HTTP libraries so every call emits structured trace events
- Routes events to one or more configurable sinks (file, console, memory, database)
- Starts an in-process HTTP listener so the UI can query and replay past runs

## Installation

```bash
cd core
pip install -e .
```

### Optional Extras

Install only the extras you need:

```bash
# Instrumentors
pip install -e ".[openai-instr]"    # OpenAI
pip install -e ".[ollama-instr]"    # Ollama
pip install -e ".[httpx-instr]"     # httpx
pip install -e ".[langchain-instr]" # LangChain

# Storage backends
pip install -e ".[sqlite-sink]"
pip install -e ".[postgres-sink]"
pip install -e ".[mysql-sink]"
pip install -e ".[mongodb-sink]"

# Development tooling
pip install -e ".[dev]"
```

## Quick Start

### 1. Create a config file

```bash
cp ../../config.example.toml config.toml
```

Configuration is loaded automatically from `config.toml` in the current working directory.

### 2. Choose a usage pattern

#### Context manager

```python
from flow_forge_ai.runtime import runtime

with runtime.run(workflow="my-workflow") as run_id:
    # instrumented calls inside this block are traced
    print(f"run_id={run_id}")
```

#### Workflow decorator

```python
from flow_forge_ai.instrumentation.workflow import workflow

@workflow(workflow_id="my-pipeline")
def pipeline():
    return "done"

pipeline()
```

#### Step decorator

```python
@workflow(workflow_id="article-summarizer")
def summarize(articles: list[str]) -> str:
    return combine([summarize_one(a) for a in articles])

@summarize.step(step_id="summarize")
def summarize_one(text: str) -> str:
    ...

@summarize.step(step_id="combine")
def combine(summaries: list[str]) -> str:
    ...
```

#### Tool tracing

```python
from flow_forge_ai.instrumentation.trace_tool import trace_tool

@trace_tool(version="v1", tool_id="knowledge_base_search")
def search_knowledge_base(query: str) -> str:
    ...
```

### 3. Run an example

Examples live in [examples/](examples/):

| Example | Instrumentation | Sink |
|---------|----------------|------|
| [01_openai_context_manager](examples/01_openai_context_manager/example.py) | OpenAI | JSONL file |
| [02_ollama_workflow_decorator](examples/02_ollama_workflow_decorator/example.py) | Ollama | SQLite |
| [03_httpx_context_manager](examples/03_httpx_context_manager/example.py) | httpx | JSONL file |
| [04_requests_workflow_decorator](examples/04_requests_workflow_decorator/example.py) | requests | JSONL file |

```bash
cd examples/02_ollama_workflow_decorator
python example.py
```

## Configuration

Configuration is TOML-based with three top-level sections.

### `[runtime]`

```toml
[runtime]
enable = true
source_sink = "sqlite log"   # sink name used by the replay manager
listener_host = "127.0.0.1"
listener_port = 7070
```

### `[[instrumentors]]`

One entry per library to auto-instrument:

```toml
[[instrumentors]]
class_path = "flow_forge_ai.instrumentation.openai_instr.OpenAIInstrumentor"

[[instrumentors]]
class_path = "flow_forge_ai.instrumentation.httpx_instr.HttpxInstrumentor"
```

### `[[sinks]]`

One entry per output destination. Multiple sinks are supported simultaneously:

```toml
[[sinks]]
name = "file log"
class_path = "flow_forge_ai.sinks.file_sink.FileSink"

[sinks.options]
class_path = "flow_forge_ai.sinks.handlers.jsonl_handler.JsonlHandler"
path = "./traces.jsonl"

[[sinks]]
name = "sqlite log"
class_path = "flow_forge_ai.sinks.database_sink.DatabaseSink"

[sinks.options]
class_path = "flow_forge_ai.sinks.handlers.sqlite_handler.SQLiteHandler"
url = "sqlite:///./runs.db"
```

### `env:` expansion in sink options

Prefix any sink option value with `env:` to read it from an environment variable at load time:

```toml
[sinks.options]
user = "env:FLOW_FORGE_DB_USER"
password = "env:FLOW_FORGE_DB_PASSWORD"
```

## Supported Instrumentors

| Class path | Library |
|-----------|---------|
| `flow_forge_ai.instrumentation.openai_instr.OpenAIInstrumentor` | `openai` |
| `flow_forge_ai.instrumentation.ollama_instr.OllamaInstrumentor` | `ollama` |
| `flow_forge_ai.instrumentation.httpx_instr.HttpxInstrumentor` | `httpx` |
| `flow_forge_ai.instrumentation.requests_instr.RequestsInstrumentor` | `requests` |

## Supported Sinks

| Class path | Storage |
|-----------|---------|
| `flow_forge_ai.sinks.file_sink.FileSink` | JSONL file |
| `flow_forge_ai.sinks.console_sink.ConsoleSink` | stdout |
| `flow_forge_ai.sinks.memory_sink.MemorySink` | in-process list |
| `flow_forge_ai.sinks.database_sink.DatabaseSink` | pluggable handler (see below) |

`DatabaseSink` delegates persistence to a handler specified via `sinks.options.class_path`:

| Handler | Backend |
|---------|---------|
| `flow_forge_ai.sinks.handlers.jsonl_handler.JsonlHandler` | JSONL file |
| `flow_forge_ai.sinks.handlers.sqlite_handler.SQLiteHandler` | SQLite |
| `flow_forge_ai.sinks.handlers.postgres_handler.PostgresHandler` | PostgreSQL |
| `flow_forge_ai.sinks.handlers.mysql_handler.MySQLHandler` | MySQL |
| `flow_forge_ai.sinks.handlers.mongodb_handler.MongoDBHandler` | MongoDB |

## Runtime Replay API

When `[runtime].enable = true`, the package starts a local HTTP listener that the UI connects to:

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/runs` | List all recorded runs |
| `GET` | `/api/steps?run_id=<id>` | List steps for a run |
| `POST` | `/api/runs/{run_id}/replay` | Start a replay |
| `GET` | `/api/runs/{run_id}/replay` | Get replay status |
| `DELETE` | `/api/runs/{run_id}/replay` | Stop a replay |

## Package Layout

```
core/
├── src/flow_forge_ai/
│   ├── runtime.py            # Runtime entry point (run context manager)
│   ├── emitter.py            # Event emitter
│   ├── context.py            # Run context
│   ├── replay.py             # Replay manager
│   ├── config/               # Config loading and models
│   ├── instrumentation/      # Instrumentors + @workflow / @trace_tool decorators
│   ├── sinks/                # Sink implementations and handlers
│   ├── internal_logging/     # Internal logger
│   └── utils/                # Shared utilities
├── examples/                 # Runnable end-to-end scenarios
└── tests/                    # Unit, integration, and e2e tests
```

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run tests with coverage
pytest --cov=flow_forge_ai --cov-report=term-missing --cov-report=xml

# Type checking
pyright

# Lint (requires enchant)
brew install enchant
pylint ./src
```
