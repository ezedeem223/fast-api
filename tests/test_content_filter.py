from types import SimpleNamespace
from unittest.mock import Mock

from app import content_filter

def make_session(words):
    query = Mock()
    query.all.return_value = words
    session = Mock()
    session.query.return_value = query
    return session


def test_check_content_classifies_by_severity():
    words = [
        SimpleNamespace(word="spoiler", severity="warn"),
        SimpleNamespace(word="forbidden", severity="ban"),
    ]
    session = make_session(words)

    warnings, bans = content_filter.check_content(
        session, "This post has a spoiler but nothing forbidden"
    )

    assert warnings == ["spoiler"]
    assert bans == ["forbidden"]


def test_filter_content_masks_words_case_insensitive():
    words = [SimpleNamespace(word="Secret", severity="warn")]
    session = make_session(words)

    filtered = content_filter.filter_content(
        session, "Keep this secret between Secret keepers"
    )

    assert "******" in filtered
    assert "Secret" not in filtered
