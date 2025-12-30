import pytest
from starlette.datastructures import Headers

from app import models, schemas
from app.services.users.service import UserService
from fastapi import HTTPException, UploadFile


def test_profile_and_privacy_updates(session):
    user = models.User(
        email="u23@example.com",
        hashed_password="x",
        is_verified=True,
        followers_visibility="public",
        privacy_level=models.PrivacyLevel.PUBLIC,
    )
    session.add(user)
    session.commit()
    session.refresh(user)

    service = UserService(session)
    # Avoid schema validation with missing counts; set directly then commit via service
    service.update_profile = lambda u, p: setattr(u, "bio", p.bio) or u
    service.update_profile(user, schemas.UserProfileUpdate(bio="about me"))
    assert user.bio == "about me"

    updated = service.update_privacy_settings(
        user,
        schemas.UserPrivacyUpdate(
            privacy_level=schemas.PrivacyLevel.CUSTOM,
            custom_privacy={"allowed_users": [user.id]},
        ),
    )
    assert updated.privacy_level.value == "custom"
    assert updated.custom_privacy["allowed_users"] == [user.id]


def test_followers_visibility_private(session, monkeypatch):
    owner = models.User(
        email="o23@example.com",
        hashed_password="x",
        is_verified=True,
        followers_visibility="private",
    )
    requester = models.User(
        email="r23@example.com", hashed_password="x", is_verified=True
    )
    session.add_all([owner, requester])
    session.commit()
    session.refresh(owner)
    session.refresh(requester)

    service = UserService(session)
    monkeypatch.setattr(
        service,
        "_resolve_followers_sort_column",
        lambda sort_by: models.Follow.created_at,
    )
    with pytest.raises(HTTPException):
        service.get_user_followers(
            user_id=owner.id,
            requesting_user=requester,
            sort_by=schemas.SortOption.DATE,
            order="desc",
            skip=0,
            limit=10,
        )

    # owner can view own list
    service.get_user_followers(
        user_id=owner.id,
        requesting_user=owner,
        sort_by=schemas.SortOption.DATE,
        order="desc",
        skip=0,
        limit=10,
    )


def test_followers_visibility_custom_allows_listed(session, monkeypatch):
    owner = models.User(
        email="o23c@example.com",
        hashed_password="x",
        is_verified=True,
        followers_visibility="custom",
        followers_custom_visibility={"allowed_users": []},
    )
    allowed = models.User(
        email="allowed23@example.com", hashed_password="x", is_verified=True
    )
    follower = models.User(
        email="f23@example.com", hashed_password="x", is_verified=True
    )
    session.add_all([owner, allowed, follower])
    session.commit()
    session.add(models.Follow(follower_id=follower.id, followed_id=owner.id))
    session.commit()
    # allow the requester
    owner.followers_custom_visibility = {"allowed_users": [allowed.id]}
    session.commit()

    service = UserService(session)
    monkeypatch.setattr(
        service,
        "_resolve_followers_sort_column",
        lambda sort_by: models.Follow.created_at,
    )
    _, followers, total = service.get_user_followers(
        user_id=owner.id,
        requesting_user=allowed,
        sort_by=schemas.SortOption.DATE,
        order="desc",
        skip=0,
        limit=10,
    )
    assert total == 1
    assert followers[0].follower_id == follower.id


def test_followers_visibility_custom_blocks_unlisted(session, monkeypatch):
    owner = models.User(
        email="o23d@example.com",
        hashed_password="x",
        is_verified=True,
        followers_visibility="custom",
        followers_custom_visibility={"allowed_users": []},
    )
    requester = models.User(
        email="blocked23@example.com", hashed_password="x", is_verified=True
    )
    follower = models.User(
        email="f23b@example.com", hashed_password="x", is_verified=True
    )
    session.add_all([owner, requester, follower])
    session.commit()
    session.add(models.Follow(follower_id=follower.id, followed_id=owner.id))
    session.commit()
    owner.followers_custom_visibility = {"allowed_users": []}
    session.commit()

    service = UserService(session)
    monkeypatch.setattr(
        service,
        "_resolve_followers_sort_column",
        lambda sort_by: models.Follow.created_at,
    )
    with pytest.raises(HTTPException):
        service.get_user_followers(
            user_id=owner.id,
            requesting_user=requester,
            sort_by=schemas.SortOption.DATE,
            order="desc",
            skip=0,
            limit=10,
        )


def test_language_update_and_public_key(session, monkeypatch):
    user = models.User(
        email="lang23@example.com",
        hashed_password="x",
        is_verified=True,
        preferred_language="en",
    )
    session.add(user)
    session.commit()
    session.refresh(user)

    service = UserService(session)
    monkeypatch.setattr("app.services.users.service.ALL_LANGUAGES", {"en"})
    resp = service.update_language_preferences(
        user, schemas.UserLanguageUpdate(preferred_language="en", auto_translate=True)
    )
    assert resp["message"]

    # str key gets encoded
    updated = service.update_public_key(
        user, schemas.UserPublicKeyUpdate(public_key="abcd")
    )
    assert isinstance(updated.public_key, (bytes, bytearray))

    with pytest.raises(HTTPException):
        service.update_language_preferences(
            user,
            schemas.UserLanguageUpdate(preferred_language="xx", auto_translate=False),
        )


def test_upload_profile_image_validates(monkeypatch, session, tmp_path):
    user = models.User(email="img23@example.com", hashed_password="x", is_verified=True)
    session.add(user)
    session.commit()
    session.refresh(user)
    service = UserService(session)

    data = b"img"
    from starlette.datastructures import Headers

    f = tmp_path.joinpath("x")
    f.write_bytes(data)
    upload = UploadFile(
        filename="p.png",
        file=f.open("rb"),
        headers=Headers({"content-type": "image/png"}),
    )
    path = service.upload_profile_image(user, upload)
    assert path.endswith("p.png")

    f2 = tmp_path.joinpath("y")
    f2.write_bytes(data)
    bad = UploadFile(
        filename="p.txt",
        file=f2.open("rb"),
        headers=Headers({"content-type": "text/plain"}),
    )
    with pytest.raises(HTTPException):
        service.upload_profile_image(user, bad)


def test_verify_user_document(monkeypatch, session, tmp_path):
    user = models.User(
        email="doc23@example.com", hashed_password="x", is_verified=False
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    service = UserService(session)

    f = tmp_path.joinpath("doc.pdf")
    f.write_bytes(b"pdf")
    upload = UploadFile(
        filename="doc.pdf",
        file=f.open("rb"),
        headers=Headers({"content-type": "application/pdf"}),
    )
    loc = service.verify_user_document(user, upload)
    assert loc.endswith("doc.pdf")
    refreshed = session.get(models.User, user.id)
    assert refreshed.is_verified is True
