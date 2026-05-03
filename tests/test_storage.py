import pytest

from prompt_registry import FileSystemStorage, PromptVersion, Run
from prompt_registry.exceptions import PromptNotFoundError, VersionNotFoundError


@pytest.fixture()
def store(tmp_path):
    return FileSystemStorage(tmp_path / "store")


def test_save_and_load_prompt_round_trip(store):
    p = PromptVersion.create(name="p", version="v1", template="t {x}")
    store.save_prompt(p)
    assert store.load_prompt("p", "v1") == p


def test_save_prompt_rejects_overwrite(store):
    p = PromptVersion.create(name="p", version="v1", template="t {x}")
    store.save_prompt(p)
    with pytest.raises(FileExistsError):
        store.save_prompt(p)


def test_load_unknown_name_raises(store):
    with pytest.raises(PromptNotFoundError):
        store.load_prompt("missing", "v1")


def test_load_unknown_version_raises(store):
    store.save_prompt(PromptVersion.create(name="p", version="v1", template="t"))
    with pytest.raises(VersionNotFoundError):
        store.load_prompt("p", "v9")


def test_save_and_list_runs(store):
    store.save_prompt(PromptVersion.create(name="p", version="v1", template="t"))
    run = Run(
        prompt_name="p",
        prompt_version="v1",
        inputs={"x": 1},
        output="ok",
        model="claude-opus-4-7",
    )
    store.save_run(run)
    listed = store.list_runs(prompt_name="p", prompt_version="v1")
    assert len(listed) == 1
    assert listed[0].output == "ok"


def test_list_runs_requires_name_when_version_given(store):
    with pytest.raises(ValueError):
        store.list_runs(prompt_version="v1")
