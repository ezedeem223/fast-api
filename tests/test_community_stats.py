from datetime import date, datetime, timedelta, timezone

from app.services.community.service import CommunityService
from app.modules.community.models import Community, CommunityMember, CommunityStatistics
from app.modules.posts.models import Post, Comment
from app.modules.social import Vote
from app.modules.users.models import User


def _setup_basic(session):
    owner = User(email="owner@x.com", hashed_password="x", is_verified=True)
    session.add(owner)
    session.commit()
    session.refresh(owner)
    community = Community(
        name="c1",
        description="d",
        language="en",
        owner_id=owner.id,
        created_at=datetime.now(timezone.utc) - timedelta(days=10),
    )
    session.add(community)
    session.commit()
    session.refresh(community)
    return owner, community


def test_update_community_statistics_counts(session):
    owner, community = _setup_basic(session)
    # members
    session.add(CommunityMember(community_id=community.id, user_id=owner.id))
    # posts and comments
    p1 = Post(title="t1", content="c", owner_id=owner.id, community_id=community.id)
    session.add(p1)
    session.commit()
    session.refresh(p1)
    session.add(Comment(content="c", owner_id=owner.id, post_id=p1.id))
    session.add(Vote(post_id=p1.id, user_id=owner.id))
    session.commit()

    service = CommunityService(session)
    stats = service.update_community_statistics(community_id=community.id)

    assert stats.member_count == 1
    assert stats.post_count == 1
    assert stats.comment_count == 1
    assert stats.total_reactions == 1
    assert stats.average_posts_per_user >= 1


def test_update_community_rankings_and_growth(session, monkeypatch):
    owner, community = _setup_basic(session)
    # attach members/posts counts
    community.members = [CommunityMember(community_id=community.id, user_id=owner.id)]
    community.posts_count = 2
    community.comment_count = 3
    community.total_reactions = 1
    community.created_at = datetime.now(timezone.utc)

    service = CommunityService(session)
    # mock growth rate
    monkeypatch.setattr(service, "calculate_community_growth_rate", lambda cid: 5)
    service.update_community_rankings()

    session.refresh(community)
    assert community.activity_score > 0
    assert community.ranking >= 0


def test_calculate_community_growth_rate_time_window(session, monkeypatch):
    owner, community = _setup_basic(session)
    now = datetime.now(timezone.utc)
    # fabricate stats: current and last month
    this_month = CommunityStatistics(
        community_id=community.id,
        date=date(year=now.year, month=now.month, day=1),
        member_count=10,
    )
    last_month_date = (now - timedelta(days=31)).date().replace(day=1)
    last_month = CommunityStatistics(
        community_id=community.id,
        date=last_month_date,
        member_count=5,
    )
    session.add_all([this_month, last_month])
    session.commit()

    service = CommunityService(session)
    growth = service.calculate_community_growth_rate(community.id)
    assert growth >= 0
