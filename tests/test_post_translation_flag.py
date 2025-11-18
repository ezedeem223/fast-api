import os
import pytest

from app import models
from app.services.posts import PostService


@pytest.fixture()
def sample_post(session, test_user):
    post = models.Post(
        title="Hola",
        content="Hola mundo",
        owner_id=test_user["id"],
    )
    session.add(post)
    session.commit()
    session.refresh(post)
    return post


@pytest.fixture(autouse=True)
def enable_translation_flag():
    previous = os.environ.get("ENABLE_TRANSLATION")
    os.environ["ENABLE_TRANSLATION"] = "1"
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("ENABLE_TRANSLATION", None)
        else:
            os.environ["ENABLE_TRANSLATION"] = previous


@pytest.mark.asyncio
async def test_list_posts_translates_when_flag_enabled(session, test_user, sample_post):
    service = PostService(session)
    user = session.get(models.User, test_user["id"])
    calls = []

    async def fake_translator(content, user_obj, language):
        calls.append((content, language))
        return f"{content}-translated"

    posts = await service.list_posts(
        current_user=user,
        limit=5,
        skip=0,
        search="",
        translate=True,
        translator_fn=fake_translator,
    )

    assert calls, "translator should be invoked when translate flag is true"
    assert posts and posts[0].content.endswith("-translated")


@pytest.mark.asyncio
async def test_list_posts_skips_translation_when_flag_disabled(session, test_user, sample_post):
    service = PostService(session)
    user = session.get(models.User, test_user["id"])
    calls = []

    async def fake_translator(content, user_obj, language):
        calls.append((content, language))
        return content

    posts = await service.list_posts(
        current_user=user,
        limit=5,
        skip=0,
        search="",
        translate=False,
        translator_fn=fake_translator,
    )

    assert posts
    assert calls == []
