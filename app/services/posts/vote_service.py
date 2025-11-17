"""Business logic for voting and reactions on posts."""

from __future__ import annotations

import asyncio
from typing import Dict

from fastapi import BackgroundTasks, HTTPException, status
from sqlalchemy.orm import Session

from app import schemas, notifications
from app.modules.posts.models import Post, Reaction
from app.modules.social.models import Vote
from app.modules.users.models import User
from app.notifications import (
    queue_email_notification,
    schedule_email_notification,
    create_notification,
)
from app.modules.utils.common import get_user_display_name
from app.modules.utils.analytics import (
    update_post_score,
    update_post_vote_statistics,
)


class VoteService:
    """Encapsulates vote/reaction workflows on posts."""

    def __init__(self, db: Session):
        self.db = db

    def vote(
        self,
        *,
        payload: schemas.ReactionCreate,
        current_user: User,
        background_tasks: BackgroundTasks,
        queue_email_fn=queue_email_notification,
        schedule_email_fn=schedule_email_notification,
        create_notification_fn=create_notification,
        notification_manager=notifications.manager,
    ) -> Dict[str, str]:
        post = self.db.query(Post).filter(Post.id == payload.post_id).first()
        if not post:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Post with id: {payload.post_id} does not exist",
            )

        existing_reaction = (
            self.db.query(Reaction)
            .filter(
                Reaction.post_id == payload.post_id,
                Reaction.user_id == current_user.id,
            )
            .first()
        )

        reaction_value = getattr(payload.reaction_type, "value", payload.reaction_type)

        if existing_reaction:
            if existing_reaction.reaction_type == payload.reaction_type:
                self.db.delete(existing_reaction)
                self.db.commit()
                message = f"Successfully removed {reaction_value} reaction"
            else:
                existing_reaction.reaction_type = payload.reaction_type
                self.db.commit()
                message = f"Successfully updated reaction to {reaction_value}"
        else:
            new_reaction = Reaction(
                user_id=current_user.id,
                post_id=payload.post_id,
                reaction_type=payload.reaction_type,
            )
            self.db.add(new_reaction)
            self.db.commit()
            message = f"Successfully added {reaction_value} reaction"

        update_post_score(self.db, post)

        queue_email_fn(
            background_tasks,
            to=post.owner.email,
            subject="New Vote on Your Post",
            body=f"Your post '{post.title}' has received a new vote.",
        )
        schedule_email_fn(
            background_tasks,
            to=post.owner.email,
            subject="New Vote on Your Post",
            body=f"Your post '{post.title}' has received a new vote.",
        )

        vote_broadcast_message = (
            f"User {current_user.id} has voted on post {post.id}."
        )
        vote_broadcast = notification_manager.broadcast
        if asyncio.iscoroutinefunction(vote_broadcast):
            background_tasks.add_task(
                asyncio.run, vote_broadcast(vote_broadcast_message)
            )
        else:
            vote_broadcast(vote_broadcast_message)

        actor_name = get_user_display_name(current_user)
        create_notification_fn(
            self.db,
            post.owner_id,
            f"{actor_name} reacted to your post with {reaction_value}",
            f"/post/{post.id}",
            "new_reaction",
            post.id,
        )

        background_tasks.add_task(
            update_post_vote_statistics, self.db, payload.post_id
        )
        return {"message": message}

    def remove_reaction(
        self,
        *,
        post_id: int,
        current_user: User,
        background_tasks: BackgroundTasks,
        queue_email_fn=queue_email_notification,
        create_notification_fn=create_notification,
    ) -> None:
        reaction_query = self.db.query(Reaction).filter(
            Reaction.post_id == post_id, Reaction.user_id == current_user.id
        )
        reaction = reaction_query.first()

        if not reaction:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Reaction not found"
            )

        reaction_query.delete(synchronize_session=False)
        self.db.commit()

        post = self.db.query(Post).filter(Post.id == post_id).first()
        update_post_score(self.db, post)

        actor_name = get_user_display_name(current_user)
        queue_email_fn(
            background_tasks,
            to=post.owner.email,
            subject="Reaction Removed from Your Post",
            body=f"A reaction has been removed from your post by user {actor_name}",
        )

        create_notification_fn(
            self.db,
            post.owner_id,
            f"{actor_name} removed their reaction from your post",
            f"/post/{post.id}",
            "removed_reaction",
            post.id,
        )

        background_tasks.add_task(update_post_vote_statistics, self.db, post_id)

    def get_vote_count(self, post_id: int) -> Dict[str, int]:
        votes = self.db.query(Vote).filter(Vote.post_id == post_id).count()
        return {"post_id": post_id, "votes": votes}

    def get_post_voters(
        self,
        *,
        post_id: int,
        current_user: User,
        skip: int,
        limit: int,
    ) -> schemas.VotersListOut:
        post = self.db.query(Post).filter(Post.id == post_id).first()
        if not post:
            raise HTTPException(status_code=404, detail="Post not found")

        if post.owner_id != current_user.id and not getattr(
            current_user, "is_moderator", False
        ):
            raise HTTPException(status_code=403, detail="Not authorized to view voters")

        voters_query = (
            self.db.query(User).join(Vote).filter(Vote.post_id == post_id)
        )
        total_count = voters_query.count()
        voters = voters_query.offset(skip).limit(limit).all()

        return schemas.VotersListOut(
            voters=[schemas.VoterOut.model_validate(voter) for voter in voters],
            total_count=total_count,
        )
