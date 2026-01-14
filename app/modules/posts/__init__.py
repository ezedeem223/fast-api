"""Posts domain public exports."""

from .models import (
    Comment,
    CopyrightType,
    LivingTestimony,
    Poll,
    PollOption,
    PollVote,
    Post,
    PostCategory,
    PostStatus,
    PostVoteStatistics,
    Reaction,
    ReactionType,
    RepostStatistics,
    SocialMediaAccount,
    SocialMediaPost,
    SocialMediaType,
    post_hashtags,
)
from .schemas import (
    EngagementStats,
    PollCreate,
    PollData,
)
from .schemas import PollOption as PollOptionSchema
from .schemas import (
    PollResults,
)
from .schemas import Post as PostSchema
from .schemas import PostBase as PostBaseSchema
from .schemas import PostCategory as PostCategorySchema
from .schemas import (
    PostCategoryBase,
    PostCategoryCreate,
)
from .schemas import PostCreate as PostCreateSchema
from .schemas import (
    PostOut,
    PostSearch,
    PostVoteAnalytics,
    PostVoteStatisticsBase,
    PostVoteStatisticsCreate,
    ReactionBase,
    ReactionCount,
    ReactionCreate,
    SocialPostBase,
    SocialPostCreate,
    SocialPostOut,
    SocialPostUpdate,
    UserVoteAnalytics,
)

__all__ = [
    "CopyrightType",
    "SocialMediaType",
    "PostStatus",
    "ReactionType",
    "Reaction",
    "Post",
    "Comment",
    "PostVoteStatistics",
    "RepostStatistics",
    "PollOption",
    "Poll",
    "PollVote",
    "PostCategory",
    "SocialMediaAccount",
    "SocialMediaPost",
    "post_hashtags",
    "LivingTestimony",
    "ReactionBase",
    "ReactionCreate",
    "ReactionCount",
    "PostVoteAnalytics",
    "PostVoteStatisticsBase",
    "PostVoteStatisticsCreate",
    "UserVoteAnalytics",
    "PostCategoryBase",
    "PostCategoryCreate",
    "PostCategorySchema",
    "PollOptionSchema",
    "PollData",
    "PollCreate",
    "PollResults",
    "PostBaseSchema",
    "PostCreateSchema",
    "PostSchema",
    "PostOut",
    "EngagementStats",
    "SocialPostBase",
    "SocialPostCreate",
    "SocialPostUpdate",
    "SocialPostOut",
    "PostSearch",
    "VoteService",
]


def __getattr__(name: str):
    """Helper for   getattr  ."""
    if name == "VoteService":
        from app.services.posts.vote_service import VoteService as _VoteService

        return _VoteService
    raise AttributeError(f"module 'app.modules.posts' has no attribute {name!r}")
