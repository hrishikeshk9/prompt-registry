from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class Run:
    """A captured model invocation tied to a specific prompt version."""

    prompt_name: str
    prompt_version: str
    inputs: dict[str, Any]
    output: str
    model: str
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    created_at: str = field(default_factory=_utcnow_iso)
    latency_ms: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "prompt_name": self.prompt_name,
            "prompt_version": self.prompt_version,
            "inputs": dict(self.inputs),
            "output": self.output,
            "model": self.model,
            "latency_ms": self.latency_ms,
            "created_at": self.created_at,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Run:
        return cls(
            prompt_name=data["prompt_name"],
            prompt_version=data["prompt_version"],
            inputs=dict(data.get("inputs") or {}),
            output=data["output"],
            model=data["model"],
            run_id=data.get("run_id", uuid.uuid4().hex[:12]),
            created_at=data.get("created_at", _utcnow_iso()),
            latency_ms=data.get("latency_ms"),
            metadata=dict(data.get("metadata") or {}),
        )
