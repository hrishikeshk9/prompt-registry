from prompt_registry import Registry


def test_bulk_import_registers_all(tmp_path):
    reg = Registry(tmp_path / "store")
    versions = reg.bulk_import({
        "summarize": "Summarize: {text}",
        "extract_entities": "Extract entities from: {text}",
        "classify": "Classify the following: {text}",
    })
    assert versions == {"summarize": "v1", "extract_entities": "v1", "classify": "v1"}
    assert sorted(reg.list_prompts()) == ["classify", "extract_entities", "summarize"]


def test_bulk_import_is_idempotent(tmp_path):
    reg = Registry(tmp_path / "store")
    prompts = {"a": "x", "b": "y"}
    reg.bulk_import(prompts)
    again = reg.bulk_import(prompts)  # same content → same versions
    assert again == {"a": "v1", "b": "v1"}
    assert reg.list_versions("a") == ["v1"]
