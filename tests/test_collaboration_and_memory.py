import datetime

from app.modules.collaboration.models import (
    CollaborativeProject,
    ProjectContribution,
    ProjectStatus,
)
from app.modules.posts.models import Post, LivingTestimony
from app.modules.social.models import ImpactCertificate, CulturalDictionaryEntry


def test_collaborative_project_and_contributions(session, test_user, test_user2):
    project = CollaborativeProject(
        title="Community Garden",
        description="Build a shared neighborhood garden",
        goals="Plan, plant, and maintain",
        owner_id=test_user.id,
        status=ProjectStatus.IN_PROGRESS,
    )
    session.add(project)
    session.flush()

    contrib1 = ProjectContribution(
        project_id=project.id,
        user_id=test_user.id,
        content="Designed the layout",
        contribution_type="design",
    )
    contrib2 = ProjectContribution(
        project_id=project.id,
        user_id=test_user2.id,
        content="Provided seeds and tools",
        contribution_type="support",
    )
    session.add_all([contrib1, contrib2])
    session.commit()

    refreshed = session.get(CollaborativeProject, project.id)
    assert refreshed.status == ProjectStatus.IN_PROGRESS
    assert len(refreshed.contributions) == 2
    assert {c.user_id for c in refreshed.contributions} == {test_user.id, test_user2.id}


def test_living_testimony_links_post_and_verifier(session, test_user, test_user2):
    post = Post(
        title="Oral history snippet",
        content="Grandparent story recorded",
        owner_id=test_user.id,
        is_encrypted=True,
        encryption_key_id="key-123",
        is_living_testimony=True,
    )
    session.add(post)
    session.flush()

    testimony = LivingTestimony(
        post_id=post.id,
        verified_by_user_id=test_user2.id,
        historical_event="Local heritage",
        geographic_location="Cairo",
        recorded_at=datetime.datetime.now(datetime.timezone.utc),
    )
    session.add(testimony)
    session.commit()

    stored = session.get(LivingTestimony, testimony.id)
    assert stored.post_id == post.id
    assert stored.verifier.id == test_user2.id
    assert stored.post.is_living_testimony is True
    assert stored.post.is_encrypted is True
    assert stored.post.encryption_key_id == "key-123"


def test_impact_certificate_and_cultural_dictionary_entries(session, test_user):
    cert = ImpactCertificate(
        user_id=test_user.id,
        title="Tree Planting",
        description="Planted 100 trees",
        impact_metrics={"trees_planted": 100},
    )
    entry = CulturalDictionaryEntry(
        term="Diwani",
        definition="A classical Arabic calligraphic script",
        cultural_context="Often used in official documents",
        language="ar",
        submitted_by=test_user.id,
        is_verified=True,
    )
    session.add_all([cert, entry])
    session.commit()

    stored_cert = session.get(ImpactCertificate, cert.id)
    stored_entry = session.get(CulturalDictionaryEntry, entry.id)
    assert stored_cert.user_id == test_user.id
    assert stored_cert.impact_metrics["trees_planted"] == 100
    assert stored_entry.term == "Diwani"
    assert stored_entry.is_verified is True
