from app.modules.utils import search as search_utils


def test_get_spell_suggestions_uses_spellchecker(monkeypatch):
    class DummySpell:
        def __contains__(self, word):
            return word in {"hello", "world"}

        def correction(self, word):
            return "hello"

    monkeypatch.setattr(search_utils, "spell", DummySpell())

    suggestions = search_utils.get_spell_suggestions("helo world")
    assert suggestions == ["hello", "world"]


def test_format_spell_suggestions_only_when_needed():
    suggestion = search_utils.format_spell_suggestions("helo", ["hello"])
    assert suggestion == "Did you mean: hello?"

    unchanged = search_utils.format_spell_suggestions("exact match", ["exact", "match"])
    assert unchanged == ""
