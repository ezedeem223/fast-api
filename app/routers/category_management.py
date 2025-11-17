from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from .. import models, schemas, oauth2
from app.modules.posts import PostCategory
from app.core.database import get_db

router = APIRouter(prefix="/categories", tags=["Categories"])


@router.post(
    "/", status_code=status.HTTP_201_CREATED, response_model=schemas.PostCategory
)
def create_category(
    category: schemas.PostCategoryCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    Create a new category.

    Parameters:
        category: Data required to create the category.
        db: Database session.
        current_user: The current authenticated user.

    Returns:
        schemas.PostCategory: The created category.

    Raises:
        HTTPException: If the current user does not have admin privileges.
    """
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Only admins can create categories")

    new_category = PostCategory(**category.model_dump())
    db.add(new_category)
    db.commit()
    db.refresh(new_category)
    return new_category


@router.put("/{category_id}", response_model=schemas.PostCategory)
def update_category(
    category_id: int,
    category: schemas.PostCategoryCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    Update an existing category.

    Parameters:
        category_id: The ID of the category to update.
        category: New data for the category.
        db: Database session.
        current_user: The current authenticated user.

    Returns:
        schemas.PostCategory: The updated category.

    Raises:
        HTTPException: If the category is not found or if the user lacks admin privileges.
    """
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Only admins can update categories")

    db_category = (
        db.query(PostCategory)
        .filter(PostCategory.id == category_id)
        .first()
    )
    if not db_category:
        raise HTTPException(status_code=404, detail="Category not found")

    for key, value in category.model_dump().items():
        setattr(db_category, key, value)

    db.commit()
    db.refresh(db_category)
    return db_category


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category(
    category_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    Delete a category.

    Parameters:
        category_id: The ID of the category to delete.
        db: Database session.
        current_user: The current authenticated user.

    Returns:
        dict: A confirmation message upon successful deletion.

    Raises:
        HTTPException: If the category is not found or if the user lacks admin privileges.
    """
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Only admins can delete categories")

    db_category = (
        db.query(PostCategory)
        .filter(PostCategory.id == category_id)
        .first()
    )
    if not db_category:
        raise HTTPException(status_code=404, detail="Category not found")

    db.delete(db_category)
    db.commit()
    return {"message": "Category deleted successfully"}


@router.get("/", response_model=List[schemas.PostCategory])
def get_categories(db: Session = Depends(get_db)):
    """
    Retrieve the list of main categories.

    Parameters:
        db: Database session.

    Returns:
        List[schemas.PostCategory]: A list of all main categories.
    """
    categories = (
        db.query(PostCategory)
        .filter(PostCategory.parent_id == None)
        .all()
    )
    return categories
