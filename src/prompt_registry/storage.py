from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import yaml

from prompt_registry.exceptions import PromptNotFoundError, VersionNotFoundError
from prompt_registry.experiment import Experiment
from prompt_registry.prompt import PromptVersion
from prompt_registry.run import Run


class Storage(ABC):
    """Pluggable backend for prompt versions, runs, aliases, and experiments.

    Implementations must keep prompt versions immutable: once `save_prompt`
    accepts a (name, version) pair, a subsequent save with the same pair
    must raise rather than overwrite.
    """

    # ----- prompts -----
    @abstractmethod
    def save_prompt(self, prompt: PromptVersion) -> None: ...

    @abstractmethod
    def load_prompt(self, name: str, version: str) -> PromptVersion: ...

    @abstractmethod
    def list_versions(self, name: str) -> list[str]: ...

    @abstractmethod
    def list_prompts(self) -> list[str]: ...

    # ----- aliases (channels for hot-deploy) -----
    @abstractmethod
    def set_alias(self, name: str, alias: str, version: str) -> None: ...

    @abstractmethod
    def get_alias(self, name: str, alias: str) -> str: ...

    @abstractmethod
    def list_aliases(self, name: str) -> dict[str, str]: ...

    @abstractmethod
    def delete_alias(self, name: str, alias: str) -> None: ...

    # ----- runs -----
    @abstractmethod
    def save_run(self, run: Run) -> None: ...

    @abstractmethod
    def list_runs(
        self,
        prompt_name: str | None = None,
        prompt_version: str | None = None,
        experiment: str | None = None,
    ) -> list[Run]: ...

    @abstractmethod
    def find_run(self, run_id: str) -> Run | None: ...

    @abstractmethod
    def update_run(self, run: Run) -> None: ...

    # ----- experiments -----
    @abstractmethod
    def save_experiment(self, exp: Experiment) -> None: ...

    @abstractmethod
    def load_experiment(self, name: str) -> Experiment: ...

    @abstractmethod
    def list_experiments(self) -> list[str]: ...


class FileSystemStorage(Storage):
    """YAML-on-disk storage. Designed to be diffable and committable to Git.

    Layout::

        <root>/
          prompts/<name>/<version>.yaml
          prompts/<name>/_aliases.yaml
          experiments/<exp_name>.yaml
          runs/<prompt_name>/<prompt_version>/<run_id>.yaml
    """

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.prompts_dir = self.root / "prompts"
        self.runs_dir = self.root / "runs"
        self.experiments_dir = self.root / "experiments"
        self.prompts_dir.mkdir(parents=True, exist_ok=True)
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self.experiments_dir.mkdir(parents=True, exist_ok=True)

    # ----- prompts -----
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
        versions = [
            PromptVersion.from_dict(_read_yaml(p))
            for p in ndir.glob("*.yaml")
            if p.name != "_aliases.yaml"
        ]
        versions.sort(key=lambda v: v.created_at)
        return [v.version for v in versions]

    def list_prompts(self) -> list[str]:
        if not self.prompts_dir.exists():
            return []
        return sorted(p.name for p in self.prompts_dir.iterdir() if p.is_dir())

    # ----- aliases -----
    def _aliases_path(self, name: str) -> Path:
        return self.prompts_dir / name / "_aliases.yaml"

    def _read_aliases(self, name: str) -> dict[str, str]:
        path = self._aliases_path(name)
        if not path.exists():
            return {}
        return dict(_read_yaml(path) or {})

    def set_alias(self, name: str, alias: str, version: str) -> None:
        # Validate the version exists; raises PromptNotFoundError / VersionNotFoundError.
        self.load_prompt(name, version)
        aliases = self._read_aliases(name)
        aliases[alias] = version
        _write_yaml(self._aliases_path(name), aliases)

    def get_alias(self, name: str, alias: str) -> str:
        aliases = self._read_aliases(name)
        if alias not in aliases:
            raise VersionNotFoundError(f"alias {name}@{alias}")
        return aliases[alias]

    def list_aliases(self, name: str) -> dict[str, str]:
        if not (self.prompts_dir / name).exists():
            raise PromptNotFoundError(name)
        return self._read_aliases(name)

    def delete_alias(self, name: str, alias: str) -> None:
        aliases = self._read_aliases(name)
        if alias not in aliases:
            raise VersionNotFoundError(f"alias {name}@{alias}")
        del aliases[alias]
        if aliases:
            _write_yaml(self._aliases_path(name), aliases)
        else:
            self._aliases_path(name).unlink(missing_ok=True)

    # ----- runs -----
    def _run_dir(self, prompt_name: str, prompt_version: str) -> Path:
        return self.runs_dir / prompt_name / prompt_version

    def _run_path(self, run: Run) -> Path:
        return self._run_dir(run.prompt_name, run.prompt_version) / f"{run.run_id}.yaml"

    def save_run(self, run: Run) -> None:
        path = self._run_path(run)
        path.parent.mkdir(parents=True, exist_ok=True)
        _write_yaml(path, run.to_dict())

    def update_run(self, run: Run) -> None:
        path = self._run_path(run)
        if not path.exists():
            raise FileNotFoundError(f"Run not found: {run.run_id}")
        _write_yaml(path, run.to_dict())

    def find_run(self, run_id: str) -> Run | None:
        for f in self.runs_dir.rglob(f"{run_id}.yaml"):
            return Run.from_dict(_read_yaml(f))
        return None

    def list_runs(
        self,
        prompt_name: str | None = None,
        prompt_version: str | None = None,
        experiment: str | None = None,
    ) -> list[Run]:
        if prompt_version is not None and prompt_name is None:
            raise ValueError("prompt_version requires prompt_name")

        if prompt_name is None:
            files = list(self.runs_dir.rglob("*.yaml"))
        else:
            base = self.runs_dir / prompt_name
            if not base.exists():
                return []
            if prompt_version is None:
                files = list(base.rglob("*.yaml"))
            else:
                vdir = base / prompt_version
                files = list(vdir.glob("*.yaml")) if vdir.exists() else []

        runs: list[Run] = [Run.from_dict(_read_yaml(f)) for f in files]

        if experiment is not None:
            runs = [r for r in runs if r.experiment == experiment]
        runs.sort(key=lambda r: r.created_at)
        return runs

    # ----- experiments -----
    def _experiment_path(self, name: str) -> Path:
        return self.experiments_dir / f"{name}.yaml"

    def save_experiment(self, exp: Experiment) -> None:
        _write_yaml(self._experiment_path(exp.name), exp.to_dict())

    def load_experiment(self, name: str) -> Experiment:
        path = self._experiment_path(name)
        if not path.exists():
            raise VersionNotFoundError(f"experiment {name}")
        return Experiment.from_dict(_read_yaml(path))

    def list_experiments(self) -> list[str]:
        if not self.experiments_dir.exists():
            return []
        return sorted(p.stem for p in self.experiments_dir.glob("*.yaml"))


def _write_yaml(path: Path, data: Any) -> None:
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)


def _read_yaml(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)
