import json
from typing import Any, Optional

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
import httpx

from flow_forge_ai.config.models import RuntimeListenerConfig
from flow_forge_ai.internal_logging.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()

_httpx_client: Optional[httpx.AsyncClient] = None # pylint: disable=invalid-name

def initialize_client(runtime_cfg: RuntimeListenerConfig) -> None:
    """Initialize the httpx client instance."""
    global _httpx_client # pylint: disable=global-statement
    _replay_listener_host = runtime_cfg.listener_host if runtime_cfg is not None else None
    _replay_listener_port = runtime_cfg.listener_port if runtime_cfg is not None else None
    _httpx_client = httpx.AsyncClient(
        base_url=f"http://{_replay_listener_host}:{_replay_listener_port}",
        timeout=5,
    )


async def _proxy_runtime_json(
    *,
    method: str,
    path: str,
    query: Optional[dict[str, Any]] = None,
    body: Optional[dict[str, Any]] = None,
) -> tuple[int, Any]:
    if _httpx_client is None:
        raise RuntimeError("HTTPX client is not initialized. Call initialize_client() first.")
    try:
        resp = await _httpx_client.request(
            method,
            url=path,
            json=body,
            params=query,
        )
        payload: Any = {}
        if resp.content:
            try:
                payload = resp.json()
            except json.JSONDecodeError:
                payload = {}
        if resp.is_error:
            if "error" not in payload:
                payload["error"] = f"Replay listener returned HTTP {resp.status_code}"
        return resp.status_code, payload
    except httpx.RequestError as exc:
        raise RuntimeError(f"Request to replay listener failed: {exc}") from exc


async def _load_runs_and_events() -> dict[str, Any]:
    status_code, payload = await _proxy_runtime_json(
        method="GET",
        path="/api/runs",
    )
    runs: list[dict[str, Any]] = payload
    selected_run: Optional[dict[str, Any]] = runs[0] if runs else None
    steps: list[dict[str, Any]] = []
    if selected_run:
        try:
            status_code, payload = await _proxy_runtime_json(
                method="GET",
                path="/api/steps",
                query={"run_id": selected_run.get("id")},
            )
            steps = payload if status_code == 200 else []
        except Exception as exc:
            logger.error(f"Failed to list steps for run '{selected_run.get('id')}': {exc}")

    return {
        "runs": runs,
        "selected_run": selected_run,
        "steps": steps,
        "events": [event for step in steps for event in step.get("events", [])],
    }


@router.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    templates = request.app.state.templates
    view = await _load_runs_and_events()

    response: HTMLResponse = templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "title": "AI Execution Infrastructure",
            "runs": view["runs"],
            "selected_run": view["selected_run"],
            "steps": view["steps"],
            "events": view["events"],
            "selected_event": view["events"][0] if view["events"] else None,
        },
    )
    return response


@router.get("/api/runs")
async def list_runs(request: Request) -> JSONResponse:
    status_code, payload = await _proxy_runtime_json(
        method="GET",
        path="/api/runs",
        query=dict(request.query_params),
    )
    return JSONResponse(payload, status_code=status_code)


@router.get("/api/steps")
async def list_steps(request: Request) -> JSONResponse:
    query_params = dict(request.query_params)
    run_id = query_params.get("run_id")
    if not run_id:
        return JSONResponse({"error": "run_id query parameter is required"}, status_code=400)

    status_code, payload = await _proxy_runtime_json(
        method="GET",
        path="/api/steps",
        query=query_params,
    )
    return JSONResponse(payload, status_code=status_code)


@router.post("/api/runs/{run_id}/replay")
async def request_replay(run_id: str, request: Request) -> JSONResponse:
    """Forward a replay request to the main process's replay listener.

    If *start_step_id* is omitted the first non-boundary step of the run is used,
    replaying the entire run from the beginning.
    """

    body = await request.json()
    status_code, payload = await _proxy_runtime_json(
        method="POST",
        path=f"/api/runs/{run_id}/replay",
        body={"start_step_id": body.get("start_step_id")},
    )
    return JSONResponse(payload, status_code=status_code)


@router.get("/api/runs/{run_id}/replay")
async def get_replay(run_id: str) -> JSONResponse:
    """Fetch replay request info for a run from the main process replay listener."""

    status_code, payload = await _proxy_runtime_json(
        method="GET",
        path=f"/api/runs/{run_id}/replay",
    )
    if status_code == 404:
        return JSONResponse({"run_id": run_id, "start_step_id": None}, status_code=200)
    return JSONResponse(payload, status_code=status_code)


@router.delete("/api/runs/{run_id}/replay")
async def cancel_replay(run_id: str) -> JSONResponse:
    """Forward a replay cancel request to the main process replay listener."""

    status_code, payload = await _proxy_runtime_json(
        method="DELETE",
        path=f"/api/runs/{run_id}/replay",
    )
    return JSONResponse(payload, status_code=status_code)
