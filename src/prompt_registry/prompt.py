from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

_PLACEHOLDER_RE = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def content_hash(template: str) -> str:
    """Stable sha256 of the prompt template, used for dedup and integrity checks."""
    return hashlib.sha256(template.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class PromptVersion:
    """A single immutable version of a named prompt."""

    name: str
    version: str
    template: str
    content_hash: str
    created_at: str = field(default_factory=_utcnow_iso)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        name: str,
        version: str,
        template: str,
        metadata: dict[str, Any] | None = None,
    ) -> PromptVersion:
        return cls(
            name=name,
            version=version,
            template=template,
            content_hash=content_hash(template),
            metadata=dict(metadata or {}),
        )

    def variables(self) -> list[str]:
        """Names of `{placeholder}` variables in the template, in order, deduped."""
        seen: dict[str, None] = {}
        for match in _PLACEHOLDER_RE.findall(self.template):
            seen.setdefault(match, None)
        return list(seen.keys())

    def render(self, **kwargs: Any) -> str:
        """Substitute placeholders. Raises KeyError on missing variables."""
        missing = [v for v in self.variables() if v not in kwargs]
        if missing:
            raise KeyError(f"Missing template variables: {missing}")
        return self.template.format(**kwargs)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "template": self.template,
            "content_hash": self.content_hash,
            "created_at": self.created_at,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PromptVersion:
        return cls(
            name=data["name"],
            version=data["version"],
            template=data["template"],
            content_hash=data["content_hash"],
            created_at=data.get("created_at", _utcnow_iso()),
            metadata=dict(data.get("metadata") or {}),
        )
