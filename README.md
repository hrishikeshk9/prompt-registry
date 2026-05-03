# prompt-registry

> Version your prompts. Capture every model output. Diff what changed.

[![CI](https://github.com/hrishikeshk9/prompt-registry/actions/workflows/ci.yml/badge.svg)](https://github.com/hrishikeshk9/prompt-registry/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

A small, dependency-light Python library for managing **prompt versions** and
the **model outputs** they produced. Designed to drop into AI/LLM workflows
that need reproducibility without standing up a service.

## Why

Prompts drift. Outputs are forgotten. By the time something regresses, you
can't reconstruct what changed — was it the template, the model, the inputs,
or the wind?

`prompt-registry` gives you a tiny, Git-friendly source of truth:

- **Content-addressed versioning** — re-registering the same template is a no-op.
- **Immutable history** — `v1`, `v2`, `v3`, never overwritten.
- **Run capture** — every model call is logged against the prompt version it used.
- **Diffable storage** — YAML files on disk, ready to commit and review in PRs.
- **Pluggable backend** — filesystem out of the box, `Storage` ABC for the rest.

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
v1 = reg.register(
    name="summarize",
    template="Summarize the following text in one sentence:\n\n{text}",
    metadata={"author": "hrishi", "intended_model": "claude-opus-4-7"},
)

# Iterate the prompt — gets v2 automatically
v2 = reg.register(
    name="summarize",
    template="You are a precise editor. Summarize the text below in exactly "
             "one sentence, preserving named entities.\n\nText:\n{text}",
)

# Re-registering identical content is a no-op
assert reg.register("summarize", v2.template).version == v2.version

# Render and call your model
rendered = v2.render(text="The quick brown fox jumps over the lazy dog.")
output = my_llm_client.complete(rendered)            # your call

# Log the run against the prompt version
reg.log_run(
    prompt_name="summarize",
    prompt_version=v2.version,
    inputs={"text": "The quick brown fox jumps over the lazy dog."},
    output=output,
    model="claude-opus-4-7",
    latency_ms=137,
    metadata={"experiment": "demo"},
)

# Inspect history
reg.list_versions("summarize")          # ['v1', 'v2']
reg.runs(prompt_name="summarize")       # list[Run]
print(reg.diff("summarize", "v1", "v2"))
```

## Storage layout

Everything lives on disk as readable YAML, designed to be committed:

```
.prompts/
├── prompts/
│   └── summarize/
│       ├── v1.yaml
│       └── v2.yaml
└── runs/
    └── summarize/
        └── v2/
            └── 2026-05-03T16-32-04+00-00__a1b2c3d4e5f6.yaml
```

A prompt file:

```yaml
name: summarize
version: v2
template: |-
  You are a precise editor. Summarize the text below ...
content_hash: 9f86d081884c7d65...
created_at: '2026-05-03T16:32:04+00:00'
metadata:
  author: hrishi
  intended_model: claude-opus-4-7
```

Diff prompts the same way you diff code: `git diff` over the registry directory.

## Pluggable backends

The `Storage` ABC is the seam. Swap the filesystem for SQLite, S3, or a
managed service without changing caller code:

```python
from prompt_registry import Registry, Storage

class SQLiteStorage(Storage):
    def save_prompt(self, prompt): ...
    def load_prompt(self, name, version): ...
    # ... implement the rest

reg = Registry(storage=SQLiteStorage("prompts.db"))
```

## API at a glance

| Method | Purpose |
|---|---|
| `Registry.register(name, template, metadata=None)` | Register or fetch existing version (content-addressed) |
| `Registry.get(name, version=None)` | Latest version, or specific |
| `Registry.list_prompts()` / `list_versions(name)` | Enumerate the registry |
| `Registry.log_run(...)` | Capture a model output against a prompt version |
| `Registry.runs(prompt_name=None, prompt_version=None)` | Query runs |
| `Registry.diff(name, va, vb)` | Unified diff between two versions |

## Design choices

- **Sequential `vN` ids over content hashes** in the public API — humans read
  PRs, hashes are kept for integrity and dedup.
- **Immutable versions** — never overwrite. If you want to change a prompt,
  register a new version.
- **YAML over JSON** — multi-line templates stay readable in diffs.
- **No model SDK dependencies** — the library never calls a model. You bring
  the client; it brings the bookkeeping.

## Roadmap

- [ ] `prompt-registry` CLI for `list`, `show`, `diff`, `runs`
- [ ] SQLite backend
- [ ] Tag aliases (e.g. `summarize@prod` → `v3`)
- [ ] Pairing with `llm-eval-harness` for regression scoring across versions

## License

MIT. See [LICENSE](LICENSE).
