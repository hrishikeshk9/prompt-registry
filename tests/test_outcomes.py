import pytest

from prompt_registry import Registry
from prompt_registry.exceptions import VersionNotFoundError


@pytest.fixture()
def reg(tmp_path):
    r = Registry(tmp_path / "store")
    r.register("p", "v1 template")
    r.register("p", "v2 template")
    return r


def _log(reg, version, *, variant=None, outcome=None):
    return reg.log_run(
        prompt_name="p",
        prompt_version=version,
        inputs={},
        output="x",
        model="claude-opus-4-7",
        experiment="exp",
        variant=variant,
        outcome=outcome,
    )


def test_record_outcome_attaches_to_existing_run(reg):
    run = _log(reg, "v1")
    updated = reg.record_outcome(run.run_id, {"thumbs_up": True, "rating": 4})
    assert updated.outcome == {"thumbs_up": True, "rating": 4}
    assert reg.runs(prompt_name="p")[0].outcome == {"thumbs_up": True, "rating": 4}


def test_record_outcome_unknown_run_raises(reg):
    with pytest.raises(VersionNotFoundError):
        reg.record_outcome("does-not-exist", {"thumbs_up": True})


def test_experiment_results_aggregates_numeric_and_boolean(reg):
    reg.create_experiment(
        "exp", "p",
        variants={"control": "v1", "treatment": "v2"},
        weights={"control": 1, "treatment": 1},
    )
    _log(reg, "v1", variant="control", outcome={"thumbs_up": True, "rating": 3})
    _log(reg, "v1", variant="control", outcome={"thumbs_up": False, "rating": 4})
    _log(reg, "v2", variant="treatment", outcome={"thumbs_up": True, "rating": 5})
    _log(reg, "v2", variant="treatment", outcome={"thumbs_up": True, "rating": 5})

    results = reg.experiment_results("exp")

    assert results["control"]["runs"] == 2
    assert results["control"]["with_outcome"] == 2
    assert results["control"]["metrics"]["thumbs_up"]["true_rate"] == 0.5
    assert results["control"]["metrics"]["rating"]["mean"] == 3.5

    assert results["treatment"]["metrics"]["thumbs_up"]["true_rate"] == 1.0
    assert results["treatment"]["metrics"]["rating"]["mean"] == 5.0


def test_experiment_results_handles_runs_without_outcome(reg):
    reg.create_experiment("exp", "p", variants={"a": "v1"})
    _log(reg, "v1", variant="a")  # no outcome
    _log(reg, "v1", variant="a", outcome={"score": 2.0})
    r = reg.experiment_results("exp")
    assert r["a"]["runs"] == 2
    assert r["a"]["with_outcome"] == 1
    assert r["a"]["metrics"]["score"]["mean"] == 2.0


def test_runs_filter_by_experiment(reg):
    _log(reg, "v1", variant="a")
    reg.log_run(  # run with no experiment
        prompt_name="p", prompt_version="v2", inputs={}, output="x", model="m"
    )
    runs = reg.runs(experiment="exp")
    assert len(runs) == 1
