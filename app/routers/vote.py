from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Response
from sqlalchemy.orm import Session
from .. import models, schemas, oauth2
from ..database import get_db
from ..notifications import schedule_email_notification
from ..utils import (
    update_post_score,
    update_post_vote_statistics,
    get_user_vote_analytics,
    create_notification,
)
from datetime import datetime, timezone

router = APIRouter(prefix="/vote", tags=["Vote"])


@router.post("/", status_code=status.HTTP_201_CREATED)
def vote(
    vote: schemas.ReactionCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    # Валидация направления голоса
    if vote.dir not in [0, 1]:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid vote direction. Must be 0 or 1.",
        )

    post = db.query(models.Post).filter(models.Post.id == vote.post_id).first()
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Post with id: {vote.post_id} does not exist",
        )

    existing_reaction = (
        db.query(models.Reaction)
        .filter(
            models.Reaction.post_id == vote.post_id,
            models.Reaction.user_id == current_user.id,
        )
        .first()
    )

    if existing_reaction:
        if existing_reaction.reaction_type == vote.reaction_type:
            # Если та же реакция, удаляем ее
            db.delete(existing_reaction)
            db.commit()
            message = f"Successfully removed {vote.reaction_type} reaction"
        else:
            # Если другая реакция, обновляем ее
            existing_reaction.reaction_type = vote.reaction_type
            db.commit()
            message = f"Successfully updated reaction to {vote.reaction_type}"
    else:
        # Создание новой реакции
        new_reaction = models.Reaction(
            user_id=current_user.id,
            post_id=vote.post_id,
            reaction_type=vote.reaction_type,
        )
        db.add(new_reaction)
        db.commit()
        message = f"Successfully added {vote.reaction_type} reaction"

    # Обновление оценки поста
    update_post_score(db, post)

    # Планирование уведомления по электронной почте
    reaction_action = "added to" if not existing_reaction else "updated on"
    background_tasks.add_task(
        schedule_email_notification,
        to=post.owner.email,
        subject="Reaction Activity on Your Post",
        body=f"A {vote.reaction_type} reaction has been {reaction_action} your post by user {current_user.id}",
    )

    # Создание уведомления для владельца поста
    create_notification(
        db,
        post.owner_id,
        f"{current_user.username} отреагировал на ваш пост: {vote.reaction_type}",
        f"/post/{post.id}",
        "new_reaction",
        post.id,
    )

    background_tasks.add_task(update_post_vote_statistics, db, vote.post_id)

    return {"message": message}


@router.delete("/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_reaction(
    post_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    reaction_query = db.query(models.Reaction).filter(
        models.Reaction.post_id == post_id, models.Reaction.user_id == current_user.id
    )
    reaction = reaction_query.first()

    if not reaction:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Reaction not found"
        )

    reaction_query.delete(synchronize_session=False)
    db.commit()

    post = db.query(models.Post).filter(models.Post.id == post_id).first()
    update_post_score(db, post)

    # Планирование уведомления по электронной почте
    background_tasks.add_task(
        schedule_email_notification,
        to=post.owner.email,
        subject="Reaction Removed from Your Post",
        body=f"A reaction has been removed from your post by user {current_user.id}",
    )

    # Создание уведомления для владельца поста
    create_notification(
        db,
        post.owner_id,
        f"{current_user.username} удалил реакцию с вашего поста",
        f"/post/{post.id}",
        "removed_reaction",
        post.id,
    )

    background_tasks.add_task(update_post_vote_statistics, db, post_id)

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{post_id}")
def get_vote_count(post_id: int, db: Session = Depends(get_db)):
    votes = db.query(models.Vote).filter(models.Vote.post_id == post_id).count()
    return {"post_id": post_id, "votes": votes}


@router.get("/{post_id}/voters", response_model=schemas.VotersListOut)
def get_post_voters(
    post_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
    skip: int = 0,
    limit: int = 50,
):
    # Проверка существования поста
    post = db.query(models.Post).filter(models.Post.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    # Проверка прав доступа
    if post.owner_id != current_user.id and not current_user.is_moderator:
        raise HTTPException(status_code=403, detail="Not authorized to view voters")

    # Получение списка проголосовавших
    voters_query = (
        db.query(models.User).join(models.Vote).filter(models.Vote.post_id == post_id)
    )
    total_count = voters_query.count()
    voters = voters_query.offset(skip).limit(limit).all()

    return schemas.VotersListOut(
        voters=[schemas.VoterOut.from_orm(voter) for voter in voters],
        total_count=total_count,
    )


# Вспомогательная функция для обновления оценки поста
def update_post_score(db: Session, post: models.Post):
    reactions = (
        db.query(models.Reaction).filter(models.Reaction.post_id == post.id).all()
    )

    # Простая система подсчета очков: каждая реакция имеет свой вес
    reaction_weights = {
        "like": 1,
        "love": 2,
        "haha": 1.5,
        "wow": 1.5,
        "sad": 1,
        "angry": 1,
    }

    score = sum(
        reaction_weights.get(reaction.reaction_type, 1) for reaction in reactions
    )

    # Учитываем количество комментариев
    score += post.comment_count * 0.5

    # Учитываем возраст поста (более новые посты получают преимущество)
    age_hours = (datetime.now(timezone.utc) - post.created_at).total_seconds() / 3600.0
    score = score / (age_hours + 2) ** 1.8

    post.score = score
    db.commit()
