# Getting Started

## Installation

Install the core package:

```bash
pip install flow-forge-ai
```

Install only the extras you need:

```bash
# Instrumentors
pip install flow-forge-ai[openai-instr]    # OpenAI
pip install flow-forge-ai[ollama-instr]    # Ollama
pip install flow-forge-ai[httpx-instr]     # httpx

# Storage backends
pip install flow-forge-ai[sqlite-sink]
pip install flow-forge-ai[postgres-sink]
pip install flow-forge-ai[mysql-sink]
pip install flow-forge-ai[mongodb-sink]

# Web UI
pip install flow-forge-ai[ui]
```

## Configuration

Copy the reference configuration template and edit it:

```bash
cp config.example.toml config.toml
```

Configuration is loaded automatically from `config.toml` in the **current working directory**.

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

Prefix any sink option value with `env:` to read it from an environment variable at load time:

```toml
[sinks.options]
user = "env:FLOW_FORGE_DB_USER"
password = "env:FLOW_FORGE_DB_PASSWORD"
```

## Usage Patterns

### Context manager

```python
from flow_forge_ai.runtime import runtime

with runtime.run(workflow="my-workflow") as run_id:
    # instrumented calls inside this block are traced
    print(f"run_id={run_id}")
```

### Workflow decorator

```python
from flow_forge_ai.instrumentation.workflow import workflow

@workflow(workflow_id="my-pipeline")
def pipeline():
    return "done"

pipeline()
```

### Step decorator

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

### Tool tracing

```python
from flow_forge_ai.instrumentation.trace_tool import trace_tool

@trace_tool(version="v1", tool_id="knowledge_base_search")
def search_knowledge_base(query: str) -> str:
    ...
```

## Browse runs in the UI

```bash
flow-forge-ai-ui
```

Open `http://127.0.0.1:8080` in your browser. See [UI](ui.md) for details.
