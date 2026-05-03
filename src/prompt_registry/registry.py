from __future__ import annotations

import difflib
from pathlib import Path
from statistics import mean
from typing import Any

from prompt_registry.exceptions import PromptNotFoundError, VersionNotFoundError
from prompt_registry.experiment import Experiment, Variant, VariantChoice
from prompt_registry.prompt import PromptVersion, content_hash
from prompt_registry.run import Run
from prompt_registry.storage import FileSystemStorage, Storage


class Registry:
    """High-level API for managing prompts, aliases, experiments, and runs.

    Content-addressed: re-registering an identical template under the same
    name returns the existing version rather than creating a new one. New
    content gets the next sequential version id (`v1`, `v2`, ...).
    """

    def __init__(self, root: str | Path | None = None, *, storage: Storage | None = None) -> None:
        if storage is None:
            if root is None:
                raise ValueError("Pass either `root` or `storage`.")
            storage = FileSystemStorage(root)
        self.storage = storage

    # ---------- prompts ----------
    def register(
        self,
        name: str,
        template: str,
        metadata: dict[str, Any] | None = None,
    ) -> PromptVersion:
        """Register a prompt template. Returns the existing version on duplicate content."""
        new_hash = content_hash(template)
        try:
            existing_versions = self.storage.list_versions(name)
        except PromptNotFoundError:
            existing_versions = []

        for vid in existing_versions:
            existing = self.storage.load_prompt(name, vid)
            if existing.content_hash == new_hash:
                return existing

        next_version = f"v{len(existing_versions) + 1}"
        prompt = PromptVersion.create(
            name=name,
            version=next_version,
            template=template,
            metadata=metadata,
        )
        self.storage.save_prompt(prompt)
        return prompt

    def get(
        self,
        name: str,
        version: str | None = None,
        *,
        alias: str | None = None,
    ) -> PromptVersion:
        """Return a specific version, the version pointed at by `alias`, or the latest."""
        if version is not None and alias is not None:
            raise ValueError("Pass either `version` or `alias`, not both.")
        if alias is not None:
            version = self.storage.get_alias(name, alias)
        if version is None:
            versions = self.storage.list_versions(name)
            if not versions:
                raise VersionNotFoundError(f"No versions registered for {name!r}")
            version = versions[-1]
        return self.storage.load_prompt(name, version)

    def list_prompts(self) -> list[str]:
        return self.storage.list_prompts()

    def list_versions(self, name: str) -> list[str]:
        return self.storage.list_versions(name)

    def diff(self, name: str, version_a: str, version_b: str) -> str:
        """Unified diff between two prompt versions of the same name."""
        a = self.storage.load_prompt(name, version_a)
        b = self.storage.load_prompt(name, version_b)
        return "".join(
            difflib.unified_diff(
                a.template.splitlines(keepends=True),
                b.template.splitlines(keepends=True),
                fromfile=f"{name}@{version_a}",
                tofile=f"{name}@{version_b}",
            )
        )

    def bulk_import(
        self,
        prompts: dict[str, str],
        *,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, str]:
        """Register many prompts at once. Returns {name: version} for each.

        Designed for one-shot migrations of hard-coded prompts into the registry.
        Identical content → existing version (idempotent), so this is safe to
        re-run.
        """
        out: dict[str, str] = {}
        for name, template in prompts.items():
            pv = self.register(name, template, metadata=metadata)
            out[name] = pv.version
        return out

    # ---------- aliases (hot deploy) ----------
    def set_alias(self, name: str, alias: str, version: str) -> None:
        """Point an alias (e.g. 'prod', 'canary') at a version. The op is the deploy."""
        self.storage.set_alias(name, alias, version)

    def get_alias(self, name: str, alias: str) -> str:
        return self.storage.get_alias(name, alias)

    def list_aliases(self, name: str) -> dict[str, str]:
        return self.storage.list_aliases(name)

    def delete_alias(self, name: str, alias: str) -> None:
        self.storage.delete_alias(name, alias)

    # ---------- experiments (A/B) ----------
    def create_experiment(
        self,
        name: str,
        prompt_name: str,
        variants: dict[str, str | dict[str, Any]],
        weights: dict[str, float] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Experiment:
        """Create or replace an experiment.

        `variants` maps variant_name → either a version id (str) or a dict
        with keys `version`, `prompt_name`, `model`, `metadata`. Equal weights
        are assigned by default.
        """
        normalized: dict[str, Variant] = {}
        for vname, v in variants.items():
            if isinstance(v, str):
                normalized[vname] = Variant(version=v)
            else:
                normalized[vname] = Variant.from_dict(v)
            # Validate referenced versions exist now, not at experiment runtime.
            target_prompt = normalized[vname].prompt_name or prompt_name
            self.storage.load_prompt(target_prompt, normalized[vname].version)

        if weights is None:
            weights = {v: 1.0 for v in normalized}

        exp = Experiment(
            name=name,
            prompt_name=prompt_name,
            variants=normalized,
            weights=weights,
            metadata=dict(metadata or {}),
        )
        self.storage.save_experiment(exp)
        return exp

    def get_experiment(self, name: str) -> Experiment:
        return self.storage.load_experiment(name)

    def list_experiments(self) -> list[str]:
        return self.storage.list_experiments()

    def choose_variant(
        self,
        experiment_name: str,
        subject_id: str | None = None,
    ) -> VariantChoice:
        return self.get_experiment(experiment_name).choose(subject_id=subject_id)

    # ---------- runs ----------
    def log_run(
        self,
        prompt_name: str,
        prompt_version: str,
        inputs: dict[str, Any],
        output: str,
        model: str,
        latency_ms: int | None = None,
        experiment: str | None = None,
        variant: str | None = None,
        outcome: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Run:
        """Persist a single model invocation against a known prompt version."""
        # Touch the prompt to confirm it exists; raises if not.
        self.storage.load_prompt(prompt_name, prompt_version)
        run = Run(
            prompt_name=prompt_name,
            prompt_version=prompt_version,
            inputs=dict(inputs),
            output=output,
            model=model,
            latency_ms=latency_ms,
            experiment=experiment,
            variant=variant,
            outcome=dict(outcome) if outcome is not None else None,
            metadata=dict(metadata or {}),
        )
        self.storage.save_run(run)
        return run

    def runs(
        self,
        prompt_name: str | None = None,
        prompt_version: str | None = None,
        experiment: str | None = None,
    ) -> list[Run]:
        return self.storage.list_runs(
            prompt_name=prompt_name,
            prompt_version=prompt_version,
            experiment=experiment,
        )

    def record_outcome(
        self,
        run_id: str,
        outcome: dict[str, Any],
    ) -> Run:
        """Attach (or overwrite) the outcome on a previously-logged run.

        Use this when feedback arrives later than the model call — e.g., a
        thumbs-up webhook, a downstream conversion event, an offline grader.
        """
        run = self.storage.find_run(run_id)
        if run is None:
            raise VersionNotFoundError(f"run {run_id}")
        updated = run.with_outcome(outcome)
        self.storage.update_run(updated)
        return updated

    # ---------- evaluation ----------
    def experiment_results(self, experiment_name: str) -> dict[str, dict[str, Any]]:
        """Aggregate run outcomes per variant for a long-horizon comparison.

        Returns `{variant_name: {"runs": int, "with_outcome": int, "metrics": {...}}}`
        where `metrics` contains `mean` for numeric outcome fields and
        `true_rate` for boolean ones. Designed to give you a defensible
        readout after collecting weeks of production runs.
        """
        exp = self.get_experiment(experiment_name)
        runs = self.runs(experiment=experiment_name)

        out: dict[str, dict[str, Any]] = {}
        for variant_name in exp.variants:
            v_runs = [r for r in runs if r.variant == variant_name]
            with_outcome = [r for r in v_runs if r.outcome]
            out[variant_name] = {
                "runs": len(v_runs),
                "with_outcome": len(with_outcome),
                "metrics": _aggregate_outcomes([r.outcome for r in with_outcome]),
            }
        return out


def _aggregate_outcomes(outcomes: list[dict[str, Any] | None]) -> dict[str, dict[str, Any]]:
    """Collect numeric means and boolean rates across a list of outcome dicts."""
    metrics: dict[str, dict[str, Any]] = {}
    if not outcomes:
        return metrics

    keys: set[str] = set()
    for o in outcomes:
        if o:
            keys.update(o.keys())

    for key in sorted(keys):
        values = [o[key] for o in outcomes if o is not None and key in o]
        if not values:
            continue
        if all(isinstance(v, bool) for v in values):
            metrics[key] = {
                "type": "boolean",
                "n": len(values),
                "true_rate": sum(values) / len(values),
            }
        elif all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in values):
            metrics[key] = {
                "type": "numeric",
                "n": len(values),
                "mean": mean(values),
                "min": min(values),
                "max": max(values),
            }
        # mixed-type or non-numeric outcomes are skipped — log them in metadata instead
    return metrics
