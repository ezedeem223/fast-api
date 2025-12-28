
from app import models
import pytest


def test_amenhotep_message_and_analytics(session, test_user):
    message = models.AmenhotepMessage(
        user_id=test_user["id"],
        message="Hello, how to learn FastAPI?",
        response="Start with official tutorial and Pydantic models.",
    )
    analytics = models.AmenhotepChatAnalytics(
        user_id=test_user["id"],
        session_id="sess-123",
        total_messages=3,
        topics_discussed=["fastapi", "pydantic"],
        session_duration=120,
        satisfaction_score=4.5,
    )

    session.add_all([message, analytics])
    session.commit()
    session.refresh(message)
    session.refresh(analytics)

    assert message.id is not None
    assert analytics.session_id == "sess-123"
    assert "fastapi" in analytics.topics_discussed
    assert analytics.total_messages == 3
    assert analytics.user_id == test_user["id"]


def test_comment_edit_history_cascade(session, test_user, test_post):
    comment = models.Comment(
        content="Original comment",
        owner_id=test_user["id"],
        post_id=test_post["id"],
    )
    session.add(comment)
    session.commit()
    session.refresh(comment)

    history = models.CommentEditHistory(
        comment_id=comment.id,
        previous_content="Original comment",
    )
    session.add(history)
    session.commit()
    session.refresh(history)

    assert history.comment_id == comment.id
    assert history.previous_content == "Original comment"
    assert len(comment.edit_history) == 1

    # ensure cascade delete removes history
    session.delete(comment)
    session.commit()
    stale_history = (
        session.query(models.CommentEditHistory)
        .filter(models.CommentEditHistory.comment_id == comment.id)
        .all()
    )
    assert stale_history == []


@pytest.fixture(autouse=True)
def mock_amenhotep_model(monkeypatch):
    """
    Prevent heavy model loading by mocking AmenhotepAI init/response.
    """
    try:
        import app.ai_chat.amenhotep as amenhotep_module
    except Exception:
        yield
        return

    class DummyAmenhotepAI:
        def __init__(self, *args, **kwargs):
            self.initialized = True

        async def generate_response(self, *args, **kwargs):
            return "mocked-response"

    monkeypatch.setattr(amenhotep_module, "AmenhotepAI", DummyAmenhotepAI)
    yield


@pytest.mark.asyncio
async def test_amenhotep_ai_mock_is_used(monkeypatch):
    import app.ai_chat.amenhotep as amenhotep_module

    ai = amenhotep_module.AmenhotepAI()
    assert getattr(ai, "initialized", False)
    resp = await ai.generate_response("hi")
    assert resp == "mocked-response"
