"""
Example 1: OpenAI instrumentation using the `with runtime.run()` context manager.

Sink: JSONL file (traces.jsonl)

This example demonstrates:
  - Automatic tracing of OpenAI chat completions
  - Custom tool tracing with @trace_tool
  - Structured run context via runtime.run()

Install dependencies:
    pip install flow_forge_ai[openai-instr]

Set environment variable:
    export OPENAI_API_KEY=<your-api-key>

Run from this directory so config.toml is picked up automatically:
    cd examples/01_openai_context_manager
    python example.py
"""

import openai

from flow_forge_ai.instrumentation.trace_tool import trace_tool
from flow_forge_ai.runtime import runtime

# runtime is auto-configured from config.toml in the current working directory.
# OpenAIInstrumentor patches the openai library at import time, so all
# client.chat.completions.create() calls are traced without any code changes.

client = openai.OpenAI(
    api_key="sk-proj-DummyKeyHere1234567890abcdefghijklmnopqrstuvwxyzABCDE",
    base_url="http://localhost:9000/v1"
)


@trace_tool(version="v1", tool_id="knowledge_base_search")
def search_knowledge_base(query: str) -> str:
    """Search a knowledge base for relevant context.

    In a real scenario this would query a vector store or search index.
    Wrapped with @trace_tool so the call emits TOOL_START / TOOL_COMPLETED
    events just like LLM calls.
    """
    # Simulated result — replace with your actual retrieval logic.
    return (
        f"[KB result for '{query}']: "
        "flow-forge-ai instruments LLM and HTTP calls and writes structured "
        "trace events to configurable sinks (files, databases, console)."
    )


def answer_question(question: str) -> str:
    """Retrieve context then ask the LLM to answer based on it."""
    context = search_knowledge_base(question)

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": "You are a helpful assistant. Use only the provided context to answer.",
            },
            {
                "role": "user",
                "content": f"Context:\n{context}\n\nQuestion: {question}",
            },
        ],
    )
    return response.choices[0].message.content or ""


def main():
    questions = [
        "What does flow-forge-ai do?",
        "Which sinks are supported?",
    ]

    # runtime.run() starts a new run, sets workflow/run/trace IDs in context,
    # emits RUN_START, and on exit emits RUN_END (or RUN_ERROR on exception).
    with runtime.run(workflow="openai-qa") as run_id:
        print(f"Run started: {run_id}\n")

        for question in questions:
            print(f"Q: {question}")
            answer = answer_question(question)
            print(f"A: {answer}\n")

    print("Trace written to traces.jsonl")
    print("Inspect with: flow-forge-ai list")


if __name__ == "__main__":
    main()
