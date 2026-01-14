"""Additional coverage for category management error branches."""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app import schemas
from app.modules.posts import PostCategory
from app.routers import category_management


def test_category_update_delete_forbidden(session):
    """Cover forbidden branches for non-admins."""
    user = SimpleNamespace(is_admin=False)
    payload = schemas.PostCategoryCreate(name="n", description="d")

    with pytest.raises(HTTPException) as exc:
        category_management.update_category(
            category_id=1, category=payload, db=session, current_user=user
        )
    assert exc.value.status_code == 403
    assert exc.value.detail == "Only admins can update categories"

    with pytest.raises(HTTPException) as exc:
        category_management.delete_category(
            category_id=1, db=session, current_user=user
        )
    assert exc.value.status_code == 403
    assert exc.value.detail == "Only admins can delete categories"


def test_category_update_delete_missing(session):
    """Cover not-found branches for update/delete."""
    admin = SimpleNamespace(is_admin=True)
    payload = schemas.PostCategoryCreate(name="n", description="d")

    with pytest.raises(HTTPException) as exc:
        category_management.update_category(
            category_id=999, category=payload, db=session, current_user=admin
        )
    assert exc.value.status_code == 404
    assert exc.value.detail == "Category not found"

    with pytest.raises(HTTPException) as exc:
        category_management.delete_category(
            category_id=999, db=session, current_user=admin
        )
    assert exc.value.status_code == 404
    assert exc.value.detail == "Category not found"


def test_category_get_categories(session):
    """Cover get_categories query branch."""
    root = PostCategory(name="root", description="root")
    child = PostCategory(name="child", description="child", parent=root)
    session.add_all([root, child])
    session.commit()

    categories = category_management.get_categories(db=session)
    assert any(category.id == root.id for category in categories)
    assert all(category.parent_id is None for category in categories)
