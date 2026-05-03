from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from prompt_registry.exceptions import PromptRegistryError


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class ExperimentError(PromptRegistryError):
    """Configuration or state error in an experiment."""


@dataclass(frozen=True)
class Variant:
    """One arm of an experiment.

    Defaults inherit from the parent Experiment when not set:
    `prompt_name` is filled in from `Experiment.prompt_name`, `model` is
    a free-form hint passed back in `VariantChoice` so callers know which
    LLM client to use.
    """

    version: str
    prompt_name: str | None = None
    model: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "prompt_name": self.prompt_name,
            "model": self.model,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Variant:
        return cls(
            version=data["version"],
            prompt_name=data.get("prompt_name"),
            model=data.get("model"),
            metadata=dict(data.get("metadata") or {}),
        )


@dataclass(frozen=True)
class VariantChoice:
    """The result of `Experiment.choose(...)` — what to actually call."""

    variant: str
    prompt_name: str
    version: str
    model: str | None = None


@dataclass(frozen=True)
class Experiment:
    """Weighted A/B (or A/B/C/...) test across prompt versions.

    Variants can point at different prompt names and models, so a single
    experiment can compare prompt iterations *or* whole model setups.
    """

    name: str
    prompt_name: str
    variants: dict[str, Variant]
    weights: dict[str, float]
    status: str = "running"  # "running" | "stopped"
    created_at: str = field(default_factory=_utcnow_iso)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.variants:
            raise ExperimentError(f"Experiment {self.name!r} has no variants")
        missing = set(self.variants) - set(self.weights)
        extra = set(self.weights) - set(self.variants)
        if missing or extra:
            raise ExperimentError(
                f"Experiment {self.name!r} weights/variants mismatch: "
                f"missing={sorted(missing)} extra={sorted(extra)}"
            )
        total = sum(self.weights.values())
        if total <= 0:
            raise ExperimentError(f"Experiment {self.name!r} weights must sum to > 0")

    def _resolve(self, variant_name: str) -> VariantChoice:
        v = self.variants[variant_name]
        return VariantChoice(
            variant=variant_name,
            prompt_name=v.prompt_name or self.prompt_name,
            version=v.version,
            model=v.model,
        )

    def choose(
        self,
        subject_id: str | None = None,
        *,
        rng: random.Random | None = None,
    ) -> VariantChoice:
        """Pick a variant.

        With `subject_id`: deterministic — the same subject always sees the
        same variant for this experiment. Critical for production A/B tests
        so a single user gets a consistent UX.

        Without `subject_id`: random — useful for offline replay/testing.
        """
        names = sorted(self.variants.keys())  # stable order for determinism
        weights = [self.weights[n] for n in names]

        if subject_id is not None:
            bucket = _bucket(self.name, subject_id)  # in [0, 1)
            cumulative = 0.0
            total = sum(weights)
            for n, w in zip(names, weights):
                cumulative += w / total
                if bucket < cumulative:
                    return self._resolve(n)
            return self._resolve(names[-1])  # float-edge fallback

        chosen = (rng or random).choices(names, weights=weights, k=1)[0]
        return self._resolve(chosen)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "prompt_name": self.prompt_name,
            "status": self.status,
            "created_at": self.created_at,
            "variants": {k: v.to_dict() for k, v in self.variants.items()},
            "weights": dict(self.weights),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Experiment:
        return cls(
            name=data["name"],
            prompt_name=data["prompt_name"],
            variants={k: Variant.from_dict(v) for k, v in data["variants"].items()},
            weights={k: float(v) for k, v in data["weights"].items()},
            status=data.get("status", "running"),
            created_at=data.get("created_at", _utcnow_iso()),
            metadata=dict(data.get("metadata") or {}),
        )


def _bucket(experiment_name: str, subject_id: str) -> float:
    """Hash (experiment, subject) → float in [0, 1).

    Using a stable hash (sha256) instead of Python's built-in `hash()` so the
    bucketing is consistent across processes and Python versions.
    """
    digest = hashlib.sha256(f"{experiment_name}:{subject_id}".encode()).digest()
    # Use first 8 bytes as a uint64, divide by 2**64
    n = int.from_bytes(digest[:8], "big")
    return n / 2**64
