import pytest

from prompt_registry import (
    PromptNotFoundError,
    Registry,
)
from prompt_registry.exceptions import VersionNotFoundError


@pytest.fixture()
def reg(tmp_path):
    return Registry(tmp_path / "store")


def test_register_assigns_sequential_versions(reg):
    a = reg.register("summarize", "Summarize: {text}")
    b = reg.register("summarize", "Summarize concisely: {text}")
    assert a.version == "v1"
    assert b.version == "v2"
    assert reg.list_versions("summarize") == ["v1", "v2"]


def test_register_is_idempotent_for_identical_content(reg):
    a = reg.register("summarize", "Summarize: {text}")
    b = reg.register("summarize", "Summarize: {text}", metadata={"ignored": True})
    assert a == b
    assert reg.list_versions("summarize") == ["v1"]


def test_get_returns_latest_by_default(reg):
    reg.register("p", "v1 template")
    reg.register("p", "v2 template")
    assert reg.get("p").version == "v2"
    assert reg.get("p", version="v1").template == "v1 template"


def test_get_unknown_prompt_raises(reg):
    with pytest.raises(PromptNotFoundError):
        reg.get("does-not-exist")


def test_get_known_prompt_unknown_version_raises(reg):
    reg.register("p", "hello")
    with pytest.raises(VersionNotFoundError):
        reg.get("p", version="v99")


def test_log_run_requires_existing_prompt(reg):
    with pytest.raises(PromptNotFoundError):
        reg.log_run(
            prompt_name="ghost",
            prompt_version="v1",
            inputs={},
            output="x",
            model="claude-opus-4-7",
        )


def test_log_and_query_runs(reg):
    p = reg.register("summarize", "Summarize: {text}")
    reg.log_run(
        prompt_name="summarize",
        prompt_version=p.version,
        inputs={"text": "hello"},
        output="Hi.",
        model="claude-opus-4-7",
        latency_ms=120,
        metadata={"tokens": 5},
    )
    reg.log_run(
        prompt_name="summarize",
        prompt_version=p.version,
        inputs={"text": "bye"},
        output="Bye.",
        model="claude-opus-4-7",
    )
    runs = reg.runs(prompt_name="summarize")
    assert len(runs) == 2
    assert {r.output for r in runs} == {"Hi.", "Bye."}
    assert runs[0].created_at <= runs[1].created_at


def test_runs_filter_by_version(reg):
    p1 = reg.register("p", "v1 {x}")
    p2 = reg.register("p", "v2 {x}")
    reg.log_run(p1.name, p1.version, {"x": 1}, "a", "m")
    reg.log_run(p2.name, p2.version, {"x": 2}, "b", "m")
    runs_v2 = reg.runs(prompt_name="p", prompt_version="v2")
    assert len(runs_v2) == 1
    assert runs_v2[0].output == "b"


def test_diff_between_versions(reg):
    reg.register("p", "Summarize: {text}\n")
    reg.register("p", "Summarize concisely: {text}\n")
    diff = reg.diff("p", "v1", "v2")
    assert "Summarize concisely" in diff
    assert "p@v1" in diff and "p@v2" in diff


def test_persistence_across_instances(tmp_path):
    root = tmp_path / "store"
    Registry(root).register("p", "Hello {name}")
    reloaded = Registry(root).get("p")
    assert reloaded.template == "Hello {name}"
    assert reloaded.version == "v1"


def test_list_prompts(reg):
    reg.register("a", "x")
    reg.register("b", "y")
    assert reg.list_prompts() == ["a", "b"]
