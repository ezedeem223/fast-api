"""Test module for test session12 sticker router."""
from io import BytesIO

import pytest
from PIL import Image

from app import models, oauth2, schemas
from app.core.database import get_db
from app.modules.stickers import models as sticker_models
from app.modules.users.models import UserRole
from app.routers import sticker
from fastapi import FastAPI, HTTPException, UploadFile
from tests.testclient import TestClient


def _build_app(session, current_user):
    """Helper for  build app."""
    app = FastAPI()
    app.include_router(sticker.router)

    def override_db():
        yield session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[oauth2.get_current_user] = lambda: current_user
    return app


@pytest.fixture
def users(session):
    """Pytest fixture for users."""
    user = models.User(
        email="st12@example.com",
        hashed_password="x",
        is_verified=True,
        role=UserRole.USER,
    )
    admin = models.User(
        email="admin12@example.com",
        hashed_password="x",
        is_verified=True,
        role=UserRole.ADMIN,
    )
    session.add_all([user, admin])
    session.commit()
    session.refresh(user)
    session.refresh(admin)
    return {"user": user, "admin": admin}


def _png_bytes():
    """Helper for  png bytes."""
    bio = BytesIO()
    Image.new("RGB", (8, 8), color="blue").save(bio, format="PNG")
    return bio.getvalue()


def test_create_pack_and_duplicate_name(users, session):
    """Test case for test create pack and duplicate name."""
    app = _build_app(session, users["user"])
    client = TestClient(app)

    resp1 = client.post("/stickers/pack", json={"name": "fun"})
    assert resp1.status_code == 201
    assert resp1.json()["name"] == "fun"
    dup = client.post("/stickers/pack", json={"name": "fun"})
    assert dup.status_code == 409
    assert dup.json()["detail"] == "Sticker pack with this name already exists"


@pytest.mark.asyncio
async def test_create_sticker_assigns_pack_and_categories(
    monkeypatch, tmp_path, users, session
):
    """Test case for test create sticker assigns pack and categories."""
    pack = sticker_models.StickerPack(name="packy", creator_id=users["user"].id)
    cat = sticker_models.StickerCategory(name="silly")
    session.add_all([pack, cat])
    session.commit()
    monkeypatch.setattr(sticker, "UPLOAD_DIRECTORY", str(tmp_path))

    png_bytes = _png_bytes()
    upload = UploadFile(file=BytesIO(png_bytes), filename="s.png")
    created = await sticker.create_sticker(
        sticker=schemas.StickerCreate(
            name="smile",
            image_url="",
            pack_id=pack.id,
            category_ids=[cat.id],
        ),
        file=upload,
        db=session,
        current_user=users["user"],
    )
    assert created.pack_id == pack.id
    assert len(created.categories) == 1


@pytest.mark.asyncio
async def test_create_sticker_in_other_users_pack_forbidden(
    monkeypatch, tmp_path, users, session
):
    """Test case for test create sticker in other users pack forbidden."""
    pack = sticker_models.StickerPack(name="alien", creator_id=users["admin"].id)
    cat = sticker_models.StickerCategory(name="othercat")
    session.add_all([pack, cat])
    session.commit()
    monkeypatch.setattr(sticker, "UPLOAD_DIRECTORY", str(tmp_path))

    with pytest.raises(HTTPException) as exc:
        await sticker.create_sticker(
            sticker=schemas.StickerCreate(
                name="intrude",
                image_url="",
                pack_id=pack.id,
                category_ids=[cat.id],
            ),
            file=UploadFile(file=BytesIO(_png_bytes()), filename="s.png"),
            db=session,
            current_user=users["user"],
        )
    assert exc.value.status_code == 404
    assert exc.value.detail == "Sticker pack not found or you don't have permission"


def test_report_sticker_and_prevent_duplicates(users, session):
    """Test case for test report sticker and prevent duplicates."""
    pack = sticker_models.StickerPack(name="reportable", creator_id=users["user"].id)
    session.add(pack)
    session.commit()
    sticker_obj = sticker_models.Sticker(
        name="victim", pack_id=pack.id, image_url="x", approved=True
    )
    session.add(sticker_obj)
    session.commit()

    app = _build_app(session, users["user"])
    client = TestClient(app)

    res = client.post(
        "/stickers/report",
        json={"sticker_id": sticker_obj.id, "reason": "spam"},
    )
    assert res.status_code == 201
    assert res.json()["sticker_id"] == sticker_obj.id
    dup = client.post(
        "/stickers/report",
        json={"sticker_id": sticker_obj.id, "reason": "spam"},
    )
    assert dup.status_code == 409
    assert dup.json()["detail"] == "You already reported this sticker"

    missing = client.post(
        "/stickers/report", json={"sticker_id": 99999, "reason": "missing"}
    )
    assert missing.status_code == 404
    assert missing.json()["detail"] == "Sticker not found"


def test_admin_toggle_sticker_visibility(users, session):
    """Test case for test admin toggle sticker visibility."""
    pack = sticker_models.StickerPack(name="togglepack", creator_id=users["admin"].id)
    session.add(pack)
    session.commit()
    sticker_obj = sticker_models.Sticker(
        name="toggle",
        pack_id=pack.id,
        image_url="url",
        approved=True,
    )
    session.add(sticker_obj)
    session.commit()
    session.refresh(sticker_obj)

    admin_app = _build_app(session, users["admin"])
    admin_client = TestClient(admin_app)
    user_client = TestClient(_build_app(session, users["user"]))

    # Disable hides from default listing
    disable = admin_client.put(f"/stickers/{sticker_obj.id}/disable")
    assert disable.status_code == 200
    list_resp = user_client.get("/stickers/")
    assert all(stk["id"] != sticker_obj.id for stk in list_resp.json())

    # Enable returns it
    enable = admin_client.put(f"/stickers/{sticker_obj.id}/enable")
    assert enable.status_code == 200
    list_after = user_client.get("/stickers/")
    assert any(stk["id"] == sticker_obj.id for stk in list_after.json())

    # Non-admin cannot toggle
    forbidden = user_client.put(f"/stickers/{sticker_obj.id}/disable")
    assert forbidden.status_code == 403
