from __future__ import annotations

import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Any


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class Run:
    """A captured model invocation tied to a specific prompt version.

    `outcome` is intentionally mutable across the run's lifetime — it can be
    set at log time or recorded later (e.g., from a thumbs-up webhook). Use
    `Run.with_outcome(...)` to produce the updated value, then persist it.
    """

    prompt_name: str
    prompt_version: str
    inputs: dict[str, Any]
    output: str
    model: str
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    created_at: str = field(default_factory=_utcnow_iso)
    latency_ms: int | None = None
    experiment: str | None = None
    variant: str | None = None
    outcome: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def with_outcome(self, outcome: dict[str, Any]) -> Run:
        return replace(self, outcome=dict(outcome))

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "prompt_name": self.prompt_name,
            "prompt_version": self.prompt_version,
            "inputs": dict(self.inputs),
            "output": self.output,
            "model": self.model,
            "latency_ms": self.latency_ms,
            "experiment": self.experiment,
            "variant": self.variant,
            "outcome": dict(self.outcome) if self.outcome is not None else None,
            "created_at": self.created_at,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Run:
        outcome_raw = data.get("outcome")
        return cls(
            prompt_name=data["prompt_name"],
            prompt_version=data["prompt_version"],
            inputs=dict(data.get("inputs") or {}),
            output=data["output"],
            model=data["model"],
            run_id=data.get("run_id", uuid.uuid4().hex[:12]),
            created_at=data.get("created_at", _utcnow_iso()),
            latency_ms=data.get("latency_ms"),
            experiment=data.get("experiment"),
            variant=data.get("variant"),
            outcome=dict(outcome_raw) if outcome_raw is not None else None,
            metadata=dict(data.get("metadata") or {}),
        )
