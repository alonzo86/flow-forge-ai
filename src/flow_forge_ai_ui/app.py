import argparse
from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator

import uvicorn
from fastapi.concurrency import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from flow_forge_ai.config.config_handler import get_config_handler
from flow_forge_ai_ui.routes import router, initialize_client


BASE_DIR = Path(__file__).parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

def format_datetime(value: str) -> str:
    return datetime.fromisoformat(value).strftime("%Y-%m-%d %H:%M:%S")


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator:
    config = get_config_handler()
    try:
        runtime_cfg = config.get_runtime_config()
    except Exception as ex:
        raise RuntimeError("Failed to load runtime configuration from config handler") from ex
    initialize_client(runtime_cfg)
    yield


app = FastAPI(
    title="AI Execution Infra UI",
    lifespan=lifespan,
)

app.include_router(router)

if STATIC_DIR.exists():
    app.mount(
        "/static",
        StaticFiles(directory=STATIC_DIR),
        name="static",
    )

templates = Jinja2Templates(directory=TEMPLATES_DIR)
templates.env.filters["format_datetime"] = format_datetime
app.state.templates = templates

def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Flow Forge AI UI.")
    parser.add_argument("-H", "--host", type=str, default="127.0.0.1", help="Host address (optional)")
    parser.add_argument("-p", "--port", type=int, default=8080, help="Port number (optional)")

    args = parser.parse_args()

    uvicorn.run(
        "flow_forge_ai_ui.app:app",
        host=args.host,
        port=args.port,
        reload=False,
    )

if __name__ == "__main__":
    main()
