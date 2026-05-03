# prompt-registry

> Version your prompts. A/B test them. Hot-deploy them. Quantify the winner.

[![CI](https://github.com/hrishikeshk9/prompt-registry/actions/workflows/ci.yml/badge.svg)](https://github.com/hrishikeshk9/prompt-registry/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

A small, dependency-light Python library for managing **prompt versions**, the
**model outputs** they produced, and the **experiments** that compare them.
Designed for AI/LLM systems that need reproducibility and iteration speed
without standing up a heavyweight platform.

## Why

In a real system you don't have one prompt — you have 60. They're hard-coded
across services. A single word change can flip results. You need to:

- Find every prompt in one place — not grep across repos.
- Roll out a prompt change **without redeploying the service**.
- A/B test a wording tweak and decide based on weeks of production data.
- Eventually run different prompts for different LLMs.

`prompt-registry` is built around those needs.

| Need | Primitive |
|---|---|
| Single source of truth | `Registry` over content-addressed YAML |
| Iteration history | Auto-incrementing `v1, v2, ...` versions, immutable |
| Hot-deploy without code change | `aliases` — `summarize@prod` points at a version |
| A/B in test and prod | `Experiment` — weighted, deterministic by `subject_id` |
| Long-horizon eval (3–6 weeks) | `Run.outcome` + `experiment_results()` aggregation |
| Multi-LLM | `Variant` carries its own `prompt_name` and `model` |

## Install

```bash
pip install prompt-registry  # once published
# or, from source
pip install -e ".[dev]"
```

## Quick start

```python
from prompt_registry import Registry

reg = Registry(".prompts")

# Register a prompt — gets v1
v1 = reg.register("summarize", "Summarize: {text}")

# Iterate — gets v2 automatically
v2 = reg.register(
    "summarize",
    "You are a precise editor. Summarize in one sentence:\n\n{text}",
)

# Re-registering identical content is a no-op
assert reg.register("summarize", v2.template).version == v2.version

# Render and call your model
prompt_text = v2.render(text="The quick brown fox.")
output = my_llm_client.complete(prompt_text)            # your call

reg.log_run(
    prompt_name="summarize", prompt_version=v2.version,
    inputs={"text": "The quick brown fox."},
    output=output, model="claude-opus-4-7", latency_ms=137,
)

print(reg.diff("summarize", "v1", "v2"))
```

## Production patterns

### 1. Hot-deploy with aliases (no code changes)

The service reads prompts via an alias, never a hard-coded version. To
deploy a new prompt, you move the alias — that's it.

```python
# Prepare the new wording (creates v3)
v3 = reg.register("summarize", new_template)

# In your service, every call looks like:
prompt = reg.get("summarize", alias="prod")     # always reads current pointer

# To "deploy": move the pointer.
reg.set_alias("summarize", "prod", "v3")        # the deploy
# Optional canary:
reg.set_alias("summarize", "canary", "v3")
```

Pair the alias with whatever propagation you have:

| Backend | Refresh model |
|---|---|
| Filesystem on shared volume / NFS | Service reads on each call (or short-cache) |
| Filesystem in a Git repo | CI deploys via `git pull` on the service |
| Object store (S3, GCS) | Service polls the manifest every N seconds |
| HTTP wrapper / DB | Implement a `Storage` subclass; alias becomes a row |

The library never opens a network connection itself. Storage is a single
ABC ([src/prompt_registry/storage.py](src/prompt_registry/storage.py)) — the
filesystem implementation is the reference; production swaps in whatever
fits your stack.

### 2. A/B testing in production

```python
exp = reg.create_experiment(
    name="summarize_concise_2026_05",
    prompt_name="summarize",
    variants={"control": "v2", "treatment": "v3"},
    weights={"control": 0.5, "treatment": 0.5},
)

# In your request handler:
choice = reg.choose_variant("summarize_concise_2026_05", subject_id=user_id)
prompt = reg.get(choice.prompt_name, version=choice.version)
output = my_llm_client.complete(prompt.render(text=text))

reg.log_run(
    prompt_name=choice.prompt_name, prompt_version=choice.version,
    inputs={"text": text}, output=output, model="claude-opus-4-7",
    experiment=exp.name, variant=choice.variant,
)
```

`subject_id` makes the bucketing **deterministic** — the same user always
sees the same variant for the duration of the experiment. Critical so a
single user doesn't get jarringly different responses on consecutive calls.
Hashing is sha256, so it's stable across processes and Python versions.

### 3. Long-horizon outcome tracking

Quality signals usually arrive **after** the model call: a thumbs-up
webhook, a downstream conversion event, an offline grader. Record them
back against the run:

```python
# Whenever the signal lands (could be hours/days later):
reg.record_outcome(run_id, {"thumbs_up": True, "edit_distance": 12})

# After 3-6 weeks of traffic:
results = reg.experiment_results("summarize_concise_2026_05")
# {
#   "control":   {"runs": 4302, "with_outcome": 3104,
#                 "metrics": {"thumbs_up": {"true_rate": 0.71, ...},
#                             "edit_distance": {"mean": 18.4, ...}}},
#   "treatment": {"runs": 4288, "with_outcome": 3091,
#                 "metrics": {"thumbs_up": {"true_rate": 0.78, ...}, ...}},
# }
```

Numeric outcomes get `mean/min/max`; booleans get `true_rate`. Plug into
your stats tool of choice for significance — the registry is honest about
what it does (descriptives, not a t-test) and stays out of statistical
opinions.

### 4. Different prompts for different LLMs

Variants carry their own `prompt_name` and `model`, so an experiment can
compare entire (prompt, model) setups, not just wording:

```python
reg.register("summarize_opus", opus_tuned_template)
reg.register("summarize_haiku", haiku_tuned_template)

reg.create_experiment(
    name="summarize_model_face_off",
    prompt_name="summarize_opus",  # default
    variants={
        "opus":  {"version": "v1", "prompt_name": "summarize_opus",
                  "model": "claude-opus-4-7"},
        "haiku": {"version": "v1", "prompt_name": "summarize_haiku",
                  "model": "claude-haiku-4-5"},
    },
    weights={"opus": 0.5, "haiku": 0.5},
)

choice = reg.choose_variant("summarize_model_face_off", subject_id=user_id)
# choice.prompt_name, choice.version, choice.model — call the right LLM with the right prompt
```

### 5. Migrating 60+ hard-coded prompts

```python
# One-shot migration. Idempotent — safe to re-run.
PROMPTS = {
    "summarize":         "Summarize: {text}",
    "extract_entities":  "Extract entities from: {text}",
    "classify_intent":   "Classify the intent: {text}",
    # ...
}
reg.bulk_import(PROMPTS, metadata={"source": "legacy_migration"})
```

Once imported, replace each hard-coded string in your services with a
`reg.get(name, alias="prod")` call. Set `prod` aliases for all of them in
one CI step:

```python
for name in reg.list_prompts():
    reg.set_alias(name, "prod", "v1")
```

## Storage layout

Everything lives on disk as readable YAML, designed to be committed to Git:

```
.prompts/
├── prompts/
│   └── summarize/
│       ├── v1.yaml
│       ├── v2.yaml
│       ├── v3.yaml
│       └── _aliases.yaml          # {prod: v3, canary: v2}
├── experiments/
│   └── summarize_concise_2026_05.yaml
└── runs/
    └── summarize/
        └── v3/
            └── a1b2c3d4e5f6.yaml
```

Diff prompts the same way you diff code: `git diff` over the registry.

## API at a glance

| Method | Purpose |
|---|---|
| `Registry.register(name, template, metadata=None)` | Register or fetch existing version (idempotent) |
| `Registry.get(name, version=None, alias=None)` | Latest, specific, or aliased version |
| `Registry.bulk_import(prompts)` | Migrate many hard-coded prompts at once |
| `Registry.set_alias(name, alias, version)` | Move an alias — this is the hot deploy |
| `Registry.create_experiment(name, prompt_name, variants, weights=None)` | Define an A/B test |
| `Registry.choose_variant(exp, subject_id=None)` | Deterministic variant pick |
| `Registry.log_run(...)` | Capture a model output (with `experiment`, `variant`, `outcome`) |
| `Registry.record_outcome(run_id, outcome)` | Late-binding feedback |
| `Registry.experiment_results(name)` | Aggregate per-variant metrics over time |
| `Registry.diff(name, va, vb)` | Unified diff between two versions |

## Design choices

- **Sequential `vN` ids over hashes** in the public API — humans read PRs.
  Hashes kept internally for integrity and dedup.
- **Immutable versions** — never overwrite. Iteration creates a new version.
- **Alias-as-deploy** — the version pointer is the unit of release, not the
  template itself. Decouples "writing a prompt" from "shipping a prompt."
- **Deterministic A/B by `subject_id`** — sha256 bucket so the same user
  always sees the same variant. Stable across processes.
- **Outcome is a dict, not a number** — record whatever you have
  (thumbs, ratings, latencies, custom scores). Aggregation does the
  obvious thing per type and stays out of stats opinions.
- **No model SDK dependencies** — the library never calls a model. You
  bring the client; it brings the bookkeeping.

## Roadmap

- [ ] `prompt-registry` CLI (`list`, `show`, `diff`, `runs`, `results`)
- [ ] SQLite and S3 storage backends
- [ ] HTTP server wrapper (`uvicorn`-style) for cross-language services
- [ ] Significance helpers (Bayesian / chi-square) on top of `experiment_results`
- [ ] Pairing with [llm-eval-harness](https://github.com/hrishikeshk9) for
      offline regression scoring across prompt versions

## License

MIT. See [LICENSE](LICENSE).
