"""
Example 5: LangChain instrumentation using a RunnableLambda pipeline.

Sink: JSONL file (traces.jsonl)

This example demonstrates:
  - Automatic tracing of LangChain Runnable.invoke() calls
  - Composing a simple pipeline from RunnableLambda stages
  - Using runtime.run() to group multiple LangChain executions under one run

Install dependencies:
    pip install flow-forge-ai[langchain-instr]

Run from this directory so config.toml is picked up automatically:
    cd examples/05_langchain_runnable_pipeline
    python example.py
"""

from langchain_core.runnables import RunnableLambda

from flow_forge_ai.runtime import runtime

TOPIC_FACTS = {
    "langchain": "LangChain provides composable building blocks for LLM applications.",
    "observability": "Observability helps teams inspect workflow behavior, latency, and failures.",
    "replay": "Replay makes it easier to reproduce and debug prior workflow executions.",
}


def lookup_topic(topic: str) -> dict[str, str]:
    """Return a small knowledge packet for the requested topic."""
    normalized_topic = topic.strip().lower()
    return {
        "topic": normalized_topic,
        "fact": TOPIC_FACTS.get(
            normalized_topic,
            "No curated fact is available yet, so return a short placeholder brief.",
        ),
    }


def format_brief(topic_context: dict[str, str]) -> str:
    """Format the lookup result into a short human-readable brief."""
    topic_name = topic_context["topic"].title()
    fact = topic_context["fact"]
    return f"Topic: {topic_name}\nBrief: {fact}"


def build_chain() -> RunnableLambda:
    """Create a two-step Runnable pipeline."""
    lookup_stage = RunnableLambda(lookup_topic)
    format_stage = RunnableLambda(format_brief)
    return lookup_stage | format_stage


def main() -> None:
    chain = build_chain()
    topics = ["langchain", "observability", "replay"]

    with runtime.run(workflow="langchain-brief-generator") as run_id:
        print(f"Run started: {run_id}\n")
        for topic in topics:
            brief = chain.invoke(topic)
            print(brief)
            print()

    print("Trace written to traces.jsonl")
    print("Inspect with: flow-forge-ai list")


if __name__ == "__main__":
    main()
