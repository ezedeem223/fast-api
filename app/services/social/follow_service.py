"""Business logic for follow/unfollow flows and follower analytics."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Dict

from sqlalchemy import asc, desc, func
from sqlalchemy.orm import Session

from app import notifications, schemas
from app.modules.posts import Comment, Post
from app.modules.social import Follow
from app.modules.users.models import User
from app.modules.utils.events import log_user_event
from app.notifications import (
    create_notification,
    queue_email_notification,
    schedule_email_notification,
)
from fastapi import BackgroundTasks, HTTPException, status


class FollowService:
    """Encapsulates follow/unfollow workflows and related analytics."""

    def __init__(self, db: Session):
        self.db = db

    def follow_user(
        self,
        *,
        background_tasks: BackgroundTasks,
        current_user: User,
        target_user_id: int,
        queue_email_fn=queue_email_notification,
        schedule_email_fn=schedule_email_notification,
        notification_manager=notifications.manager,
        create_notification_fn=create_notification,
    ) -> Dict[str, str]:
        if getattr(current_user, "is_suspended", False):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Suspended users cannot follow others",
            )
        if target_user_id == current_user.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You cannot follow yourself",
            )

        user_to_follow = self.db.query(User).filter(User.id == target_user_id).first()
        if not user_to_follow:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User to follow not found",
            )

        existing_follow = (
            self.db.query(Follow)
            .filter(
                Follow.follower_id == current_user.id,
                Follow.followed_id == target_user_id,
            )
            .first()
        )
        if existing_follow:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You already follow this user",
            )

        new_follow = Follow(
            follower_id=current_user.id,
            followed_id=target_user_id,
        )
        self.db.add(new_follow)

        mutual_follow = (
            self.db.query(Follow)
            .filter(
                Follow.follower_id == target_user_id,
                Follow.followed_id == current_user.id,
            )
            .first()
        )
        if mutual_follow:
            new_follow.is_mutual = True
            mutual_follow.is_mutual = True

        user_to_follow.followers_count += 1
        current_user.following_count += 1

        self.db.commit()
        log_user_event(
            self.db, current_user.id, "follow_user", {"followed_id": target_user_id}
        )

        queue_email_fn(
            background_tasks,
            to=user_to_follow.email,
            subject="New Follower",
            body=f"User {current_user.email} is now following you.",
        )
        schedule_email_fn(
            background_tasks,
            to=user_to_follow.email,
            subject="New Follower",
            body=f"User {current_user.email} is now following you.",
        )

        broadcast_message = (
            f"User {current_user.id} has followed User {target_user_id}."
        )
        follower_broadcast = notification_manager.broadcast
        if asyncio.iscoroutinefunction(follower_broadcast):
            background_tasks.add_task(
                asyncio.run, follower_broadcast(broadcast_message)
            )
        else:
            follower_broadcast(broadcast_message)

        follower_identity = (
            getattr(current_user, "username", None) or current_user.email
        )
        create_notification_fn(
            self.db,
            target_user_id,
            f"{follower_identity} started following you",
            f"/profile/{current_user.id}",
            "new_follower",
            current_user.id,
        )

        return {"message": "Successfully followed user"}

    def unfollow_user(
        self,
        *,
        background_tasks: BackgroundTasks,
        current_user: User,
        target_user_id: int,
        queue_email_fn=queue_email_notification,
    ) -> None:
        follow = (
            self.db.query(Follow)
            .filter(
                Follow.follower_id == current_user.id,
                Follow.followed_id == target_user_id,
            )
            .first()
        )
        if not follow:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="You do not follow this user",
            )

        user_unfollowed = self.db.query(User).filter(User.id == target_user_id).first()
        if not user_unfollowed:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User to unfollow not found",
            )

        if follow.is_mutual:
            mutual_follow = (
                self.db.query(Follow)
                .filter(
                    Follow.follower_id == target_user_id,
                    Follow.followed_id == current_user.id,
                )
                .first()
            )
            if mutual_follow:
                mutual_follow.is_mutual = False

        self.db.delete(follow)
        user_unfollowed.followers_count -= 1
        current_user.following_count -= 1
        self.db.commit()

        queue_email_fn(
            background_tasks,
            to=user_unfollowed.email,
            subject="Follower Lost",
            body=f"You have lost a follower: {current_user.email}",
        )

    def get_followers(
        self,
        *,
        current_user: User,
        sort_by: str,
        order: str,
        skip: int,
        limit: int,
    ) -> Dict[str, list]:
        query = self.db.query(Follow).filter(Follow.followed_id == current_user.id)
        order_column = Follow.created_at
        if sort_by == "username":
            order_column = User.email

        query = (
            query.order_by(desc(order_column))
            if order == "desc"
            else query.order_by(asc(order_column))
        )

        total_count = query.count()
        followers = (
            query.join(User, Follow.follower_id == User.id)
            .offset(skip)
            .limit(limit)
            .all()
        )

        return {
            "followers": [
                schemas.FollowerOut(
                    id=follow.follower.id,
                    username=getattr(follow.follower, "username", None)
                    or follow.follower.email,
                    follow_date=follow.created_at,
                    post_count=follow.follower.post_count,
                    interaction_count=follow.follower.interaction_count,
                    is_mutual=follow.is_mutual,
                )
                for follow in followers
            ],
            "total_count": total_count,
        }

    def get_following(
        self,
        *,
        current_user: User,
        sort_by: str,
        order: str,
        skip: int,
        limit: int,
    ) -> Dict[str, list]:
        query = self.db.query(Follow).filter(Follow.follower_id == current_user.id)
        order_column = Follow.created_at
        if sort_by == "username":
            order_column = User.email

        query = (
            query.order_by(desc(order_column))
            if order == "desc"
            else query.order_by(asc(order_column))
        )

        total_count = query.count()
        following = (
            query.join(User, Follow.followed_id == User.id)
            .offset(skip)
            .limit(limit)
            .all()
        )

        return {
            "following": [
                schemas.FollowingOut(
                    id=follow.followed.id,
                    username=getattr(follow.followed, "username", None)
                    or follow.followed.email,
                    email=follow.followed.email,
                    follow_date=follow.created_at,
                    is_mutual=follow.is_mutual,
                )
                for follow in following
            ],
            "total_count": total_count,
        }

    def get_follow_statistics(self, *, current_user: User) -> Dict[str, object]:
        thirty_days_ago = datetime.now() - timedelta(days=30)
        daily_growth = (
            self.db.query(func.date(Follow.created_at), func.count())
            .filter(Follow.followed_id == current_user.id)
            .filter(Follow.created_at >= thirty_days_ago)
            .group_by(func.date(Follow.created_at))
            .all()
        )

        interaction_rate = (
            self.db.query(func.count(Post.id) + func.count(Comment.id))
            .filter(
                (Post.owner_id == current_user.id)
                | (Comment.owner_id == current_user.id)
            )
            .scalar()
            / current_user.followers_count
            if current_user.followers_count > 0
            else 0
        )

        return {
            "followers_count": current_user.followers_count,
            "following_count": current_user.following_count,
            "daily_growth": dict(daily_growth),
            "interaction_rate": interaction_rate,
        }

    def get_mutual_followers(self, *, current_user: User):
        return (
            self.db.query(User)
            .join(Follow, User.id == Follow.follower_id)
            .filter(Follow.followed_id == current_user.id)
            .filter(Follow.is_mutual.is_(True))
            .all()
        )
