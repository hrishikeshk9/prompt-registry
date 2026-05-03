from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import yaml

from prompt_registry.exceptions import PromptNotFoundError, VersionNotFoundError
from prompt_registry.prompt import PromptVersion
from prompt_registry.run import Run


class Storage(ABC):
    """Pluggable backend for prompt versions and runs.

    Implementations must keep prompt versions immutable: once `save_prompt`
    accepts a (name, version) pair, a subsequent save with the same pair
    must raise rather than overwrite.
    """

    @abstractmethod
    def save_prompt(self, prompt: PromptVersion) -> None: ...

    @abstractmethod
    def load_prompt(self, name: str, version: str) -> PromptVersion: ...

    @abstractmethod
    def list_versions(self, name: str) -> list[str]:
        """Return version ids for `name` in registration order, oldest first."""

    @abstractmethod
    def list_prompts(self) -> list[str]: ...

    @abstractmethod
    def save_run(self, run: Run) -> None: ...

    @abstractmethod
    def list_runs(
        self,
        prompt_name: str | None = None,
        prompt_version: str | None = None,
    ) -> list[Run]: ...


class FileSystemStorage(Storage):
    """YAML-on-disk storage. Designed to be diffable and committable to Git.

    Layout::

        <root>/
          prompts/<name>/<version>.yaml
          runs/<name>/<version>/<created_at>__<run_id>.yaml
    """

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.prompts_dir = self.root / "prompts"
        self.runs_dir = self.root / "runs"
        self.prompts_dir.mkdir(parents=True, exist_ok=True)
        self.runs_dir.mkdir(parents=True, exist_ok=True)

    def _prompt_path(self, name: str, version: str) -> Path:
        return self.prompts_dir / name / f"{version}.yaml"

    def save_prompt(self, prompt: PromptVersion) -> None:
        path = self._prompt_path(prompt.name, prompt.version)
        if path.exists():
            raise FileExistsError(
                f"Prompt version already exists: {prompt.name}@{prompt.version}"
            )
        path.parent.mkdir(parents=True, exist_ok=True)
        _write_yaml(path, prompt.to_dict())

    def load_prompt(self, name: str, version: str) -> PromptVersion:
        path = self._prompt_path(name, version)
        if not path.exists():
            if not (self.prompts_dir / name).exists():
                raise PromptNotFoundError(name)
            raise VersionNotFoundError(f"{name}@{version}")
        return PromptVersion.from_dict(_read_yaml(path))

    def list_versions(self, name: str) -> list[str]:
        ndir = self.prompts_dir / name
        if not ndir.exists():
            raise PromptNotFoundError(name)
        versions = [PromptVersion.from_dict(_read_yaml(p)) for p in ndir.glob("*.yaml")]
        versions.sort(key=lambda v: v.created_at)
        return [v.version for v in versions]

    def list_prompts(self) -> list[str]:
        if not self.prompts_dir.exists():
            return []
        return sorted(p.name for p in self.prompts_dir.iterdir() if p.is_dir())

    def save_run(self, run: Run) -> None:
        rdir = self.runs_dir / run.prompt_name / run.prompt_version
        rdir.mkdir(parents=True, exist_ok=True)
        # Filename is sortable by timestamp, then disambiguated by run_id.
        safe_ts = run.created_at.replace(":", "-")
        path = rdir / f"{safe_ts}__{run.run_id}.yaml"
        _write_yaml(path, run.to_dict())

    def list_runs(
        self,
        prompt_name: str | None = None,
        prompt_version: str | None = None,
    ) -> list[Run]:
        if prompt_version is not None and prompt_name is None:
            raise ValueError("prompt_version requires prompt_name")

        if prompt_name is None:
            search_dirs = [d for d in self.runs_dir.iterdir() if d.is_dir()]
        else:
            base = self.runs_dir / prompt_name
            if not base.exists():
                return []
            if prompt_version is None:
                search_dirs = [d for d in base.iterdir() if d.is_dir()]
            else:
                vdir = base / prompt_version
                search_dirs = [vdir] if vdir.exists() else []

        runs: list[Run] = []
        for d in search_dirs:
            for f in d.glob("*.yaml"):
                runs.append(Run.from_dict(_read_yaml(f)))
        runs.sort(key=lambda r: r.created_at)
        return runs


def _write_yaml(path: Path, data: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)


def _read_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)
