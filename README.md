<div align="center">

<img src="logo.png" alt="Flow Forge AI logo" width="240" />

# Flow Forge AI

Build, trace, and replay AI workflows with pluggable instrumentation and storage backends.

[![flow-forge-ai release](https://img.shields.io/github/v/release/alonzo86/flow-forge-ai?filter=core-v*)](https://github.com/alonzo86/flow-forge-ai/releases)
[![flow-forge-ai-ui release](https://img.shields.io/github/v/release/alonzo86/flow-forge-ai?filter=ui-v*)](https://github.com/alonzo86/flow-forge-ai/releases)
[![PyPI](https://img.shields.io/pypi/v/flow-forge-ai-sdk)](#packages)
[![Python](https://img.shields.io/pypi/pyversions/flow-forge-ai-sdk)](#packages)
[![CI](https://github.com/alonzo86/flow-forge-ai/actions/workflows/ci.yml/badge.svg)](#development)
[![codecov](https://codecov.io/gh/alonzo86/flow-forge-ai/branch/main/graph/badge.svg)](https://codecov.io/gh/alonzo86/flow-forge-ai)
[![Type Checking: mypy](https://img.shields.io/badge/type%20checking-mypy-2C5BB4)](#development)
[![UI: FastAPI](https://img.shields.io/badge/ui-fastapi-009688?logo=fastapi&logoColor=white)](#packages)
[![Docs](https://img.shields.io/badge/docs-online-blue)](https://alonzo86.github.io/flow-forge-ai/)

</div>

## Overview

Flow Forge AI is a monorepo that provides end-to-end observability for AI workflows. It automatically traces LLM calls, tool invocations, and HTTP interactions into structured events, then lets you browse and replay them through a web UI.

## Packages

| Package | Description | Docs |
|---------|-------------|------|
| [`flow-forge-ai`](core/) | Core runtime, instrumentation, and storage | [core/README.md](core/README.md) |
| [`flow-forge-ai-ui`](ui/) | FastAPI web UI for browsing and replaying runs | [ui/README.md](ui/README.md) |

## Architecture

```mermaid
flowchart LR
    A[Your Workflow Code] --> B[Runtime]
    B --> C[Instrumentors]
    C --> D[Event Emitter]
    D --> E[Sink Router]
    E --> F[File / JSONL]
    E --> G[Console]
    E --> H[SQLite / Postgres / MySQL / MongoDB]
    H --> I[Replay Manager]
    I --> J[Runtime Listener API]
    J --> K[Web UI]
```

## Quick Start

### 1. Install

```bash
# From the core package directory
cd core
pip install -e ".[openai-instr,sqlite-sink,ui]"
```

### 2. Configure

```bash
cp config.example.toml config.toml
```

### 3. Run an example

```bash
cd core/examples/02_ollama_workflow_decorator
python example.py
```

### 4. Browse runs in the UI

```bash
flow-forge-ai-ui
```

Open `http://127.0.0.1:8080` in your browser.

## Repository Layout

```
flow-forge-ai/
├── config.example.toml    # Reference configuration template
├── core/                  # flow-forge-ai package (runtime, instrumentation, sinks)
│   ├── src/flow_forge_ai/
│   ├── examples/          # Runnable end-to-end scenarios
│   └── tests/
└── ui/                    # flow-forge-ai-ui package (FastAPI web UI)
    ├── src/flow_forge_ai_ui/
    └── tests/
```

## Development

Each package is developed independently. From the package directory:

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run tests with coverage
pytest --cov=flow_forge_ai --cov-report=term-missing

# Type checking
pyright

# Lint
pylint ./src
```

See [core/README.md](core/README.md) and [ui/README.md](ui/README.md) for package-specific details.
