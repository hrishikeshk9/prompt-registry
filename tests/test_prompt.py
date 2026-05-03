import pytest

from prompt_registry.prompt import PromptVersion, content_hash


def test_content_hash_is_stable():
    assert content_hash("hello") == content_hash("hello")
    assert content_hash("hello") != content_hash("world")


def test_variables_are_extracted_in_order_and_deduped():
    p = PromptVersion.create(
        name="t", version="v1", template="Hi {name}, you are {role}. Yes {name}."
    )
    assert p.variables() == ["name", "role"]


def test_render_substitutes_variables():
    p = PromptVersion.create(name="t", version="v1", template="Hi {name}")
    assert p.render(name="Hrishi") == "Hi Hrishi"


def test_render_raises_on_missing_variables():
    p = PromptVersion.create(name="t", version="v1", template="Hi {name}, {role}")
    with pytest.raises(KeyError):
        p.render(name="Hrishi")


def test_round_trip_dict():
    p = PromptVersion.create(
        name="t", version="v1", template="x {a}", metadata={"author": "h"}
    )
    restored = PromptVersion.from_dict(p.to_dict())
    assert restored == p
