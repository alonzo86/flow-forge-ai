"""
Example 4: requests instrumentation using @workflow and @workflow.step decorators.

Sink: MongoDB (flow_forge_events database)

This example demonstrates:
  - @workflow as a self-contained entry-point that manages the run lifecycle
  - @workflow.step to assign stable step IDs to distinct pipeline stages
  - Automatic tracing of requests.Session HTTP calls
  - max_body_bytes to limit how much response body is stored per event

Install dependencies:
    pip install flow_forge_ai[mongodb-sink]

Requires a running MongoDB instance. Update the uri in config.toml if needed.

Run from this directory so config.toml is picked up automatically:
    cd examples/04_requests_workflow_decorator
    python example.py
"""

import os

os.environ["EXAMPLE4_MONGODB_USERNAME"] = "admin"
os.environ["EXAMPLE4_MONGODB_PASSWORD"] = "secretpassword"
import requests

from flow_forge_ai.instrumentation.workflow import workflow

# runtime is auto-configured from config.toml in the current working directory.
# RequestsInstrumentor patches requests.Session.request() so every HTTP call
# inside the workflow emits LLM_REQUEST / LLM_RESPONSE events automatically.

GITHUB_API = "https://api.github.com"
HEADERS = {"Accept": "application/vnd.github.v3+json"}


@workflow(workflow_id="github-trending-report")
def build_trending_report(org: str) -> str:
    """Full pipeline: fetch repos, enrich each with language stats, build report.

    Decorating with @workflow means calling build_trending_report(org) is
    equivalent to:

        with runtime.run(workflow="github-trending-report"):
            repos = fetch_top_repos(org)
            enriched = enrich_repos(repos)
            return format_report(enriched, org)
    """
    repos = fetch_top_repos(org)
    enriched = enrich_repos(repos)
    return format_report(enriched, org)


@build_trending_report.step(step_id="fetch_repos")
def fetch_top_repos(org: str) -> list[dict]:
    """Step 1 — retrieve the top-starred public repositories for an org."""
    response = requests.get(
        f"{GITHUB_API}/orgs/{org}/repos",
        headers=HEADERS,
        params={"per_page": 5, "sort": "stars", "type": "public"},
        timeout=10,
    )
    response.raise_for_status()
    return response.json()


@build_trending_report.step(step_id="enrich_repos")
def enrich_repos(repos: list[dict]) -> list[dict]:
    """Step 2 — fetch language breakdown for each repository.

    Each GET /repos/{owner}/{repo}/languages call is individually traced,
    all grouped under the same step_id='enrich_repos'.
    """
    enriched = []
    for repo in repos:
        owner = repo["owner"]["login"]
        name = repo["name"]
        lang_response = requests.get(
            f"{GITHUB_API}/repos/{owner}/{name}/languages",
            headers=HEADERS,
            timeout=10,
        )
        languages = list(lang_response.json().keys()) if lang_response.ok else []
        enriched.append({**repo, "top_languages": languages})
    return enriched


@build_trending_report.step(step_id="format_report")
def format_report(repos: list[dict], org: str) -> str:
    """Step 3 — format the collected data into a human-readable report."""
    lines = [f"Top repositories for '{org}':", ""]
    for repo in repos:
        stars = repo.get("stargazers_count", 0)
        languages = ", ".join(repo.get("top_languages", [])) or "N/A"
        lines.append(f"  {repo['name']:<40} {stars:>6} ★   [{languages}]")
    return "\n".join(lines)


def main():
    report = build_trending_report("python")

    print(report)
    print("\nEvents saved to MongoDB (flow_forge_events)")
    print("Inspect with: flow-forge-ai list")


if __name__ == "__main__":
    main()
