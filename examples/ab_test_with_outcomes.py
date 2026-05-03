"""End-to-end demo of the production patterns:

1. Bulk-import legacy hard-coded prompts.
2. Iterate to a new version.
3. Set up an A/B experiment.
4. Simulate production traffic with deterministic variant routing.
5. Record outcomes and aggregate per-variant metrics.

Run from the repo root:

    pip install -e .
    python examples/ab_test_with_outcomes.py
"""

from __future__ import annotations

import random

from prompt_registry import Registry


def fake_llm(prompt_text: str, model: str) -> str:
    return f"[{model}] {prompt_text[:30]}..."


def fake_user_thumbs_up(variant: str) -> bool:
    """Simulate users liking the treatment variant slightly more."""
    base_rate = 0.65 if variant == "treatment" else 0.55
    return random.random() < base_rate


def main() -> None:
    random.seed(42)
    reg = Registry(".prompts")

    # 1) One-shot migration of legacy prompts.
    legacy = {
        "summarize":         "Summarize: {text}",
        "extract_entities":  "Extract entities from: {text}",
        "classify_intent":   "Classify the intent of this user message: {text}",
    }
    reg.bulk_import(legacy, metadata={"source": "legacy_migration"})
    print(f"Imported {len(legacy)} prompts: {reg.list_prompts()}")

    # Set everything live on the 'prod' alias in one sweep.
    for name in reg.list_prompts():
        reg.set_alias(name, "prod", "v1")

    # 2) Iterate `summarize` to a tighter v2.
    reg.register(
        "summarize",
        "You are a precise editor. Summarize the text below in exactly one "
        "sentence, preserving named entities.\n\nText:\n{text}",
    )
    print(f"summarize versions: {reg.list_versions('summarize')}")

    # 3) Set up the A/B test (50/50, control=v1, treatment=v2).
    exp = reg.create_experiment(
        name="summarize_concise_2026_05",
        prompt_name="summarize",
        variants={"control": "v1", "treatment": "v2"},
        weights={"control": 0.5, "treatment": 0.5},
    )
    print(f"Experiment created: {exp.name}")

    # 4) Simulate production traffic from 400 users, 1 call each.
    for i in range(400):
        user_id = f"user_{i}"
        choice = reg.choose_variant(exp.name, subject_id=user_id)
        prompt = reg.get(choice.prompt_name, version=choice.version)
        rendered = prompt.render(text=f"Sample input from {user_id}")
        output = fake_llm(rendered, model="claude-opus-4-7")

        run = reg.log_run(
            prompt_name=choice.prompt_name,
            prompt_version=choice.version,
            inputs={"text": f"Sample input from {user_id}"},
            output=output,
            model="claude-opus-4-7",
            experiment=exp.name,
            variant=choice.variant,
            metadata={"subject_id": user_id},
        )

        # 5) Outcome arrives later (via webhook, etc.) — record against run_id.
        reg.record_outcome(run.run_id, {"thumbs_up": fake_user_thumbs_up(choice.variant)})

    # 6) Aggregate the readout. After weeks of real traffic this is your
    #    quantified comparison.
    results = reg.experiment_results(exp.name)
    print("\n=== Experiment results ===")
    for variant, stats in results.items():
        true_rate = stats["metrics"]["thumbs_up"]["true_rate"]
        print(
            f"  {variant:10s}  runs={stats['runs']:4d}  "
            f"with_outcome={stats['with_outcome']:4d}  "
            f"thumbs_up_rate={true_rate:.3f}"
        )

    # 7) Hot deploy the winner — change the alias, no code change needed.
    winner = max(results.items(), key=lambda kv: kv[1]["metrics"]["thumbs_up"]["true_rate"])
    winner_name, _ = winner
    winner_version = exp.variants[winner_name].version
    reg.set_alias("summarize", "prod", winner_version)
    print(f"\nDeployed winner: summarize@prod -> {winner_version} ({winner_name})")


if __name__ == "__main__":
    main()
