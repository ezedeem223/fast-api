from datetime import datetime, timedelta, timezone

from app import models
from app.modules.community import models as community_models


def test_reel_lifecycle_and_view_counts(session, test_user, test_user2):
    community = models.Community(name="Video Hub", description="Short videos")
    session.add(community)
    session.commit()
    session.refresh(community)

    reel = models.Reel(
        title="FastAPI Tips",
        video_url="http://cdn.local/reel.mp4",
        description="Quick tips",
        owner_id=test_user["id"],
        community_id=community.id,
        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
        view_count=0,
    )
    session.add(reel)
    session.commit()
    session.refresh(reel)

    reel.view_count += 1
    session.commit()
    session.refresh(reel)

    assert reel.owner_id == test_user["id"]
    assert reel.community_id == community.id
    assert reel.view_count == 1
    assert reel.is_active is True

    # ensure cascade delete from community removes reel
    session.delete(community)
    session.commit()
    leftover = session.query(models.Reel).filter_by(id=reel.id).first()
    assert leftover is None


def test_article_and_archive_with_museum_items(session, test_user, test_user2):
    community = models.Community(name="Writers Guild", description="Articles hub")
    session.add(community)
    session.commit()
    session.refresh(community)

    article = models.Article(
        title="Scaling FastAPI",
        content="Use async DB and background tasks wisely.",
        author_id=test_user["id"],
        community_id=community.id,
    )
    archive = community_models.CommunityArchive(
        community_id=community.id, name="History Vault", description="Milestones"
    )
    session.add_all([article, archive])
    session.commit()
    session.refresh(article)
    session.refresh(archive)

    item = community_models.DigitalMuseumItem(
        archive_id=archive.id,
        title="First Release",
        media_url="http://cdn.local/img.png",
        historical_context="Project launch screenshot",
        curated_by=test_user2["id"],
    )
    session.add(item)
    session.commit()
    session.refresh(item)

    assert article.author_id == test_user["id"]
    assert item.archive_id == archive.id
    assert item.curated_by == test_user2["id"]
    assert item.historical_context.startswith("Project launch")

    session.delete(archive)
    session.commit()
    assert (
        session.query(community_models.DigitalMuseumItem)
        .filter_by(id=item.id)
        .first()
        is None
    )
