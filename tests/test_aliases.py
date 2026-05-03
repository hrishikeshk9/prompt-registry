import pytest

from prompt_registry import PromptNotFoundError, Registry
from prompt_registry.exceptions import VersionNotFoundError


@pytest.fixture()
def reg(tmp_path):
    return Registry(tmp_path / "store")


def test_set_get_alias(reg):
    p = reg.register("summarize", "Summarize: {text}")
    reg.set_alias("summarize", "prod", p.version)
    assert reg.get_alias("summarize", "prod") == "v1"
    assert reg.get("summarize", alias="prod").version == "v1"


def test_alias_can_be_repointed_for_hot_deploy(reg):
    p1 = reg.register("p", "v1 template")
    p2 = reg.register("p", "v2 template")
    reg.set_alias("p", "prod", p1.version)
    assert reg.get("p", alias="prod").template == "v1 template"
    reg.set_alias("p", "prod", p2.version)
    assert reg.get("p", alias="prod").template == "v2 template"


def test_set_alias_rejects_unknown_version(reg):
    reg.register("p", "x")
    with pytest.raises(VersionNotFoundError):
        reg.set_alias("p", "prod", "v99")


def test_get_alias_unknown_raises(reg):
    reg.register("p", "x")
    with pytest.raises(VersionNotFoundError):
        reg.get_alias("p", "prod")


def test_list_aliases_requires_known_prompt(reg):
    with pytest.raises(PromptNotFoundError):
        reg.list_aliases("missing")


def test_delete_alias(reg):
    reg.register("p", "x")
    reg.set_alias("p", "prod", "v1")
    reg.delete_alias("p", "prod")
    assert reg.list_aliases("p") == {}


def test_get_rejects_both_version_and_alias(reg):
    reg.register("p", "x")
    reg.set_alias("p", "prod", "v1")
    with pytest.raises(ValueError):
        reg.get("p", version="v1", alias="prod")


def test_aliases_survive_persistence(tmp_path):
    Registry(tmp_path / "s").register("p", "x")
    Registry(tmp_path / "s").set_alias("p", "prod", "v1")
    assert Registry(tmp_path / "s").get("p", alias="prod").version == "v1"
