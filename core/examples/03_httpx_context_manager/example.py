"""
Example 3: httpx instrumentation using the `with runtime.run()` context manager.

Sinks: PostgreSQL database + JSONL file (events go to both simultaneously)

This example demonstrates:
  - Automatic tracing of all httpx HTTP calls (headers, body, status)
  - max_body_bytes to cap how much of the response body is stored per event
  - Routing events to multiple sinks at once (PostgreSQL + file)
  - Nested Span context for grouping related HTTP calls under the same trace

Install dependencies:
    pip install flow_forge_ai[httpx-instr,postgres-sink]

Set environment variables for the PostgreSQL connection:
    export DB_HOST=localhost
    export DB_PORT=5432
    export DB_NAME=flow_forge_events
    export DB_USER=postgres
    export DB_PASSWORD=secret

Update config.toml with your actual database credentials, then run from
this directory so config.toml is picked up automatically:
    cd examples/03_httpx_context_manager
    python example.py
"""

import httpx

from flow_forge_ai.context import Span
from flow_forge_ai.runtime import runtime

# runtime is auto-configured from config.toml in the current working directory.
# HttpxInstrumentor patches httpx.Client.send() and AsyncClient.send() so every
# request/response pair is captured as LLM_REQUEST / LLM_RESPONSE events.

BASE_URL = "https://api.open-meteo.com/v1"

CITIES = {
    "Paris":   (48.8566, 2.3522),
    "Berlin":  (52.5200, 13.4050),
    "Tokyo":   (35.6762, 139.6503),
}


def fetch_current_weather(client: httpx.Client, city: str, lat: float, lon: float) -> dict:
    """Fetch current weather for one city."""
    response = client.get(
        f"{BASE_URL}/forecast",
        params={
            "latitude": lat,
            "longitude": lon,
            "current_weather": True,
        },
    )
    response.raise_for_status()
    data = response.json()
    return {
        "city": city,
        "temperature_c": data["current_weather"]["temperature"],
        "wind_kmh": data["current_weather"]["windspeed"],
    }


def main():
    with httpx.Client(timeout=10) as http_client:
        # runtime.run() scopes all traced events under one run_id.
        with runtime.run(workflow="weather-reporter") as run_id:
            print(f"Run started: {run_id}\n")

            results = []

            for city, (lat, lon) in CITIES.items():
                # Span groups the HTTP call for this city under its own span_id
                # while keeping the same trace_id for the whole run.
                with Span(name=f"fetch-{city.lower()}", new_trace=False):
                    weather = fetch_current_weather(http_client, city, lat, lon)
                    results.append(weather)

            for r in results:
                print(f"{r['city']:8s}  {r['temperature_c']:>5.1f}°C  {r['wind_kmh']:>5.1f} km/h")

    print("\nEvents saved to PostgreSQL and traces.jsonl")
    print("Inspect with: flow-forge-ai list")


if __name__ == "__main__":
    main()
