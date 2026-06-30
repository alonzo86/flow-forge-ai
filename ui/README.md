# flow-forge-ai-ui

Web UI for browsing and replaying [flow-forge-ai](../core/) workflow runs.

[![PyPI](https://img.shields.io/pypi/v/flow-forge-ai-sdk)](#packages)
[![Python](https://img.shields.io/pypi/pyversions/flow-forge-ai-sdk)](#packages)
[![CI](https://github.com/alonzo86/flow-forge-ai/actions/workflows/ci.yml/badge.svg)](#development)
[![codecov](https://codecov.io/gh/alonzo86/flow-forge-ai/branch/main/graph/badge.svg)](https://codecov.io/gh/alonzo86/flow-forge-ai)
[![Type Checking: mypy](https://img.shields.io/badge/type%20checking-mypy-2C5BB4)](#development)
[![UI: FastAPI](https://img.shields.io/badge/ui-fastapi-009688?logo=fastapi&logoColor=white)](#packages)

## What It Does

- Connects to the runtime listener started by `flow-forge-ai`
- Displays a list of recorded runs and their steps/events
- Lets you trigger and monitor workflow replays from the browser

## Requirements

- `flow-forge-ai` installed and configured with `[runtime].enable = true`
- The runtime listener must be reachable at the configured `listener_host:listener_port`

## Installation

### Install the package and its dependencies:

```bash
pip install flow-forge-ai[ui]
```

### For development
```bash
cd ui
pip install -e .
```

Or install via the `ui` extra from the core package:

```bash
cd core
pip install -e ".[ui]"
```

## Starting the UI

```bash
flow-forge-ai-ui
```

By default the server listens on `http://127.0.0.1:8080`.

### Options

```
flow-forge-ai-ui --host 0.0.0.0 --port 9090
```

| Flag | Default | Description |
|------|---------|-------------|
| `-H` / `--host` | `127.0.0.1` | Bind address |
| `-p` / `--port` | `8080` | Port |

## Configuration

The UI reads `config.toml` from the **current working directory** (the same file used by the core runtime). It uses the `[runtime]` section to locate the listener:

```toml
[runtime]
enable = true
listener_host = "127.0.0.1"
listener_port = 7070
```

Make sure the runtime listener is started before opening the UI. The core package starts the listener automatically when a workflow run begins inside an instrumented process.

## Usage

1. Start your workflow in another terminal (the core runtime listener starts automatically):

   ```bash
   cd core/examples/02_ollama_workflow_decorator
   python example.py
   ```

2. Start the UI from the directory containing `config.toml`:

   ```bash
   flow-forge-ai-ui
   ```

3. Open `http://127.0.0.1:8080` in your browser.

The UI shows all recorded runs. Select a run to inspect its steps and events, or trigger a replay.

## API Routes

The UI itself is a thin FastAPI app that proxies requests to the core runtime listener. It exposes the following routes:

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Main UI page (HTML) |
| `GET` | `/api/runs` | Proxy: list runs |
| `GET` | `/api/steps` | Proxy: list steps for a run |
| `POST` | `/api/runs/{run_id}/replay` | Proxy: start replay |
| `GET` | `/api/runs/{run_id}/replay` | Proxy: get replay status |
| `DELETE` | `/api/runs/{run_id}/replay` | Proxy: stop replay |

## Package Layout

```
ui/
├── src/flow_forge_ai_ui/
│   ├── app.py          # FastAPI app factory and CLI entry point
│   ├── routes.py       # Route handlers and runtime proxy client
│   ├── templates/      # Jinja2 HTML templates
│   └── static/         # JS and static assets
└── tests/
```

## Development

```bash
# Install dev dependencies (from core package which includes UI dev deps)
cd core
pip install -e ".[dev]"

# Run UI tests
cd ui
pytest

# Run tests with coverage
pytest --cov=flow_forge_ai_ui --cov-report=term-missing
```
