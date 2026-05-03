import pytest

from prompt_registry import ExperimentError, Registry
from prompt_registry.exceptions import VersionNotFoundError


@pytest.fixture()
def reg(tmp_path):
    r = Registry(tmp_path / "store")
    r.register("summarize", "v1 template")
    r.register("summarize", "v2 template")
    return r


def test_create_experiment_with_string_variants(reg):
    exp = reg.create_experiment(
        name="exp1",
        prompt_name="summarize",
        variants={"control": "v1", "treatment": "v2"},
        weights={"control": 0.3, "treatment": 0.7},
    )
    assert exp.name == "exp1"
    assert set(exp.variants) == {"control", "treatment"}


def test_create_experiment_default_equal_weights(reg):
    exp = reg.create_experiment(
        "exp", "summarize", {"a": "v1", "b": "v2"}
    )
    assert exp.weights == {"a": 1.0, "b": 1.0}


def test_create_experiment_validates_versions(reg):
    with pytest.raises(VersionNotFoundError):
        reg.create_experiment("bad", "summarize", {"a": "v99"})


def test_experiment_rejects_mismatched_weights(reg):
    with pytest.raises(ExperimentError):
        reg.create_experiment(
            "bad", "summarize", {"a": "v1", "b": "v2"}, weights={"a": 1.0}
        )


def test_choose_variant_is_deterministic_per_subject(reg):
    reg.create_experiment("exp", "summarize", {"a": "v1", "b": "v2"})
    pick1 = reg.choose_variant("exp", subject_id="user_42")
    pick2 = reg.choose_variant("exp", subject_id="user_42")
    assert pick1 == pick2


def test_choose_variant_distribution_roughly_matches_weights(reg):
    reg.create_experiment(
        "exp", "summarize",
        {"a": "v1", "b": "v2"},
        weights={"a": 0.2, "b": 0.8},
    )
    counts = {"a": 0, "b": 0}
    for i in range(2000):
        choice = reg.choose_variant("exp", subject_id=f"user_{i}")
        counts[choice.variant] += 1
    rate_b = counts["b"] / sum(counts.values())
    # Expect ~0.8; allow a generous margin so the test isn't flaky.
    assert 0.74 < rate_b < 0.86, counts


def test_choose_returns_correct_routing(reg):
    reg.create_experiment(
        "exp", "summarize",
        variants={"a": {"version": "v2", "model": "claude-opus-4-7"}},
    )
    choice = reg.choose_variant("exp", subject_id="any")
    assert choice.variant == "a"
    assert choice.prompt_name == "summarize"
    assert choice.version == "v2"
    assert choice.model == "claude-opus-4-7"


def test_experiment_can_route_across_prompt_names(reg):
    """Multi-LLM pattern: variants point to whole different prompt+model setups."""
    reg.register("summarize_haiku", "haiku-tuned template")
    reg.create_experiment(
        "model_face_off",
        prompt_name="summarize",  # default for variants without override
        variants={
            "opus": {"version": "v2", "model": "claude-opus-4-7"},
            "haiku": {
                "version": "v1",
                "prompt_name": "summarize_haiku",
                "model": "claude-haiku-4-5",
            },
        },
    )
    haiku = reg.get_experiment("model_face_off").variants["haiku"]
    assert haiku.prompt_name == "summarize_haiku"
    assert haiku.model == "claude-haiku-4-5"
