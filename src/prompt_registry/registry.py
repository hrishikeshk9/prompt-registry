from __future__ import annotations

import difflib
from pathlib import Path
from typing import Any

from prompt_registry.exceptions import PromptNotFoundError, VersionNotFoundError
from prompt_registry.prompt import PromptVersion, content_hash
from prompt_registry.run import Run
from prompt_registry.storage import FileSystemStorage, Storage


class Registry:
    """High-level API for managing prompts and the runs they produced.

    The registry is content-addressed: re-registering an identical template
    under the same name returns the existing version rather than creating a
    new one. New content gets the next sequential version id (`v1`, `v2`, ...).
    """

    def __init__(self, root: str | Path | None = None, *, storage: Storage | None = None) -> None:
        if storage is None:
            if root is None:
                raise ValueError("Pass either `root` or `storage`.")
            storage = FileSystemStorage(root)
        self.storage = storage

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

    def get(self, name: str, version: str | None = None) -> PromptVersion:
        """Return a specific version, or the latest if `version` is None."""
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

    def log_run(
        self,
        prompt_name: str,
        prompt_version: str,
        inputs: dict[str, Any],
        output: str,
        model: str,
        latency_ms: int | None = None,
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
            metadata=dict(metadata or {}),
        )
        self.storage.save_run(run)
        return run

    def runs(
        self,
        prompt_name: str | None = None,
        prompt_version: str | None = None,
    ) -> list[Run]:
        return self.storage.list_runs(prompt_name=prompt_name, prompt_version=prompt_version)

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
