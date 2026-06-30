# Examples

Runnable end-to-end examples live in [`core/examples/`](https://github.com/alonzo86/flow-forge-ai/tree/main/core/examples).

| Example | Instrumentation | Sink |
|---------|----------------|------|
| `01_openai_context_manager` | OpenAI | JSONL file |
| `02_ollama_workflow_decorator` | Ollama | SQLite |
| `03_httpx_context_manager` | httpx | JSONL file |
| `04_requests_workflow_decorator` | requests | JSONL file |

All examples are run from the example directory so `config.toml` is picked up automatically:

```bash
cd core/examples/<example-dir>
python example.py
```

---

## 01 — OpenAI context manager

Demonstrates automatic tracing of OpenAI chat completions and custom tool tracing with `@trace_tool`, using the `with runtime.run()` context manager.

**Install**

```bash
pip install flow-forge-ai[openai-instr]
```

**Run**

```bash
cd core/examples/01_openai_context_manager
export OPENAI_API_KEY=<your-api-key>
python example.py
```

**Key snippet**

```python
import openai
from flow_forge_ai.instrumentation.trace_tool import trace_tool
from flow_forge_ai.runtime import runtime

client = openai.OpenAI()

@trace_tool(version="v1", tool_id="knowledge_base_search")
def search_knowledge_base(query: str) -> str:
    return "[KB result]"

with runtime.run(workflow="my-workflow") as run_id:
    context = search_knowledge_base("What is flow-forge-ai?")
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": context}],
    )
```

---

## 02 — Ollama workflow decorator

Demonstrates the `@workflow` and `@workflow.step` decorators with automatic tracing of all `ollama.chat()` calls. Persists traces to SQLite.

**Install**

```bash
pip install flow-forge-ai[ollama-instr]
```

Requires a running Ollama server:

```bash
ollama pull tinyllama
```

**Run**

```bash
cd core/examples/02_ollama_workflow_decorator
python example.py
```

**Key snippet**

```python
import ollama
from flow_forge_ai.instrumentation.workflow import workflow

@workflow(workflow_id="ollama-article-summarizer")
def summarize_articles(articles: list[str]) -> str:
    summaries = [summarize_single(a) for a in articles]
    return combine_summaries(summaries)

@summarize_articles.step(step_id="summarize")
def summarize_single(text: str) -> str:
    response = ollama.chat(
        model="tinyllama",
        messages=[{"role": "user", "content": f"Summarize: {text}"}],
    )
    return response["message"]["content"]

@summarize_articles.step(step_id="combine")
def combine_summaries(summaries: list[str]) -> str:
    ...
```

---

## 03 — httpx context manager

Demonstrates automatic tracing of outbound HTTP requests made with `httpx`, using the `with runtime.run()` context manager.

**Install**

```bash
pip install flow-forge-ai[httpx-instr]
```

**Run**

```bash
cd core/examples/03_httpx_context_manager
python example.py
```

---

## 04 — requests workflow decorator

Demonstrates automatic tracing of outbound HTTP requests made with the `requests` library, using the `@workflow` decorator.

**Install**

```bash
pip install flow-forge-ai
```

**Run**

```bash
cd core/examples/04_requests_workflow_decorator
python example.py
```
