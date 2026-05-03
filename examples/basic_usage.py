"""Minimal end-to-end demo of registering a prompt and logging a run.

Run from the repo root:

    pip install -e .
    python examples/basic_usage.py
"""

from prompt_registry import Registry


def fake_llm_call(prompt_text: str, model: str) -> tuple[str, int]:
    """Stand-in for a real model call. Returns (output, latency_ms)."""
    return f"[{model}] {prompt_text[:40]}...", 137


def main() -> None:
    reg = Registry(".prompts")

    v1 = reg.register(
        name="summarize",
        template="Summarize the following text in one sentence:\n\n{text}",
        metadata={"author": "hrishi", "intended_model": "claude-opus-4-7"},
    )
    print(f"Registered {v1.name}@{v1.version}  hash={v1.content_hash[:10]}")

    # Iterate the prompt — a new version is created automatically.
    v2 = reg.register(
        name="summarize",
        template=(
            "You are a precise editor. Summarize the text below in exactly one "
            "sentence, preserving named entities.\n\nText:\n{text}"
        ),
        metadata={"author": "hrishi", "intended_model": "claude-opus-4-7"},
    )
    print(f"Registered {v2.name}@{v2.version}  hash={v2.content_hash[:10]}")

    # Re-registering identical content is a no-op.
    again = reg.register(name="summarize", template=v2.template)
    assert again.version == v2.version

    # Render and "call the model".
    rendered = v2.render(text="The quick brown fox jumps over the lazy dog.")
    output, latency = fake_llm_call(rendered, model="claude-opus-4-7")

    run = reg.log_run(
        prompt_name=v2.name,
        prompt_version=v2.version,
        inputs={"text": "The quick brown fox jumps over the lazy dog."},
        output=output,
        model="claude-opus-4-7",
        latency_ms=latency,
        metadata={"experiment": "demo"},
    )
    print(f"Logged run {run.run_id} for {run.prompt_name}@{run.prompt_version}")

    print("\nVersions:", reg.list_versions("summarize"))
    print(f"Total runs: {len(reg.runs(prompt_name='summarize'))}")
    print("\nDiff v1 → v2:\n")
    print(reg.diff("summarize", "v1", "v2"))


if __name__ == "__main__":
    main()
