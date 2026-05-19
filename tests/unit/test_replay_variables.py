from __future__ import annotations

from lucid.replayer.semantic_replay import apply_variables


def test_string_substitution() -> None:
    out = apply_variables("Merhaba {{musteri}}", {"musteri": "Acme Corp"})
    assert out == "Merhaba Acme Corp"


def test_unknown_placeholder_preserved() -> None:
    out = apply_variables("tutar: {{tutar}} TL", {"musteri": "x"})
    assert out == "tutar: {{tutar}} TL"


def test_recursive_dict_and_list() -> None:
    tree = {
        "text": "merhaba {{name}}",
        "keys": ["{{k1}}", "enter"],
        "nested": {"value": "{{k2}} yazdı"},
    }
    out = apply_variables(tree, {"name": "Alex", "k1": "ctrl", "k2": "Sam"})
    assert out["text"] == "merhaba Alex"
    assert out["keys"] == ["ctrl", "enter"]
    assert out["nested"]["value"] == "Sam yazdı"


def test_non_string_scalars_unchanged() -> None:
    assert apply_variables(42, {"foo": "bar"}) == 42
    assert apply_variables(None, {"foo": "bar"}) is None
