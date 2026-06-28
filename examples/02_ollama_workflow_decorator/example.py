"""
Example 2: Ollama instrumentation using @workflow and @workflow.step decorators.

Sink: SQLite database (runs.db)

This example demonstrates:
  - @workflow decorator as a drop-in replacement for `with runtime.run()`
  - @workflow.step to label individual logical steps within a workflow
  - Automatic tracing of all ollama.chat() calls

Install dependencies:
    pip install flow_forge_ai[ollama-instr]

Requires a running Ollama server with the llama3 model:
    ollama pull llama3

Run from this directory so config.toml is picked up automatically:
    cd examples/02_ollama_workflow_decorator
    python example.py
"""

import ollama

from flow_forge_ai.instrumentation.workflow import workflow

# runtime is auto-configured from config.toml in the current working directory.
# OllamaInstrumentor patches the ollama library so all ollama.chat() /
# ollama.generate() calls are traced automatically.


@workflow(workflow_id="ollama-article-summarizer")
def summarize_articles(articles: list[str]) -> str:
    """Top-level workflow function.

    Calling summarize_articles() is equivalent to:

        with runtime.run(workflow="ollama-article-summarizer") as run_id:
            ...

    Each decorated @workflow.step call is tagged with its step_id in the
    emitted events, making it easy to group and filter traces per step.
    """
    summaries = [summarize_single(article) for article in articles]
    return combine_summaries(summaries)


@summarize_articles.step(step_id="summarize")
def summarize_single(text: str) -> str:
    """Summarize one article in a single sentence."""
    response = ollama.chat(
        model="tinyllama",
        messages=[
            {"role": "user", "content": f"Summarize the following in one sentence:\n\n{text}"},
        ],
    )
    return response["message"]["content"]


@summarize_articles.step(step_id="combine")
def combine_summaries(summaries: list[str]) -> str:
    """Merge individual summaries into a short paragraph."""
    bullet_list = "\n".join(f"- {s}" for s in summaries)
    response = ollama.chat(
        model="tinyllama",
        messages=[
            {
                "role": "user",
                "content": (
                    "Combine the following bullet-point summaries into a "
                    f"single coherent paragraph:\n\n{bullet_list}"
                ),
            },
        ],
    )
    return response["message"]["content"]


def main():
    articles = [
        (
            "Artificial intelligence is transforming healthcare by enabling faster "
            "diagnosis through medical image analysis and predictive analytics."
        ),
        (
            "Climate scientists report record-breaking temperatures across multiple "
            "continents, urging immediate action on carbon emissions."
        ),
        (
            "New quantum computing breakthroughs promise exponential speedups for "
            "combinatorial optimization and cryptography."
        ),
    ]

    result = summarize_articles(articles)

    print("Final summary:\n")
    print(result)
    print("\nEvents saved to runs.db (SQLite)")
    print("Inspect with: flow-forge-ai list")


if __name__ == "__main__":
    main()
