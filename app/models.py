"""Legacy compatibility layer aggregating SQLAlchemy models.

The application has been modularised under ``app.modules``. This file keeps the
original ``app.models`` import path working by re-exporting the models,
enums, and association tables from their domain packages. New code should
import directly from the relevant module package.
"""

# 1. التعديل الجوهري: استيراد Base من Core Database
from app.core.database import Base

from app.modules.users.associations import post_mentions, user_hashtag_follows
from app.modules.community.associations import community_tags
from app.modules.stickers import sticker_category_association

from app.modules.users.models import (
    UserType,
    VerificationStatus,
    PrivacyLevel,
    UserRole,
    User,
    TokenBlacklist,
    UserActivity,
    UserEvent,
    UserSession,
    UserStatistics,
)

from app.modules.community import (
    CommunityRole,
    CommunityCategory,
    Community,
    CommunityMember,
    CommunityStatistics,
    CommunityRule,
    CommunityInvitation,
    Category,
    SearchSuggestion,
    SearchStatistics,
    Tag,
    Reel,
    Article,
)

from app.modules.posts import (
    CopyrightType,
    SocialMediaType,
    PostStatus,
    ReactionType,
    Reaction,
    Post,
    Comment,
    PostVoteStatistics,
    RepostStatistics,
    PollOption,
    Poll,
    PollVote,
    PostCategory,
    SocialMediaAccount,
    SocialMediaPost,
    post_hashtags,
    LivingTestimony,
)

from app.modules.notifications.models import (
    NotificationStatus,
    NotificationPriority,
    NotificationCategory,
    NotificationType,
    NotificationPreferences,
    NotificationGroup,
    Notification,
    NotificationDeliveryAttempt,
    NotificationAnalytics,
    NotificationDeliveryLog,
)

from app.modules.messaging import (
    CallType,
    CallStatus,
    MessageType,
    ScreenShareStatus,
    ConversationType,
    ConversationMemberRole,
    Conversation,
    ConversationMember,
    Message,
    MessageAttachment,
    EncryptedSession,
    EncryptedCall,
    Call,
    ScreenShareSession,
    ConversationStatistics,
)

from app.modules.support import TicketStatus, SupportTicket, TicketResponse

from app.modules.stickers import (
    StickerPack,
    Sticker,
    StickerCategory,
    StickerReport,
)

from app.modules.moderation import (
    BlockDuration,
    BlockType,
    AppealStatus,
    UserWarning,
    UserBan,
    IPBan,
    BannedWord,
    BanStatistics,
    BanReason,
    Block,
    BlockLog,
    BlockAppeal,
)

from app.modules.amenhotep import (
    AmenhotepMessage,
    AmenhotepChatAnalytics,
    CommentEditHistory,
)

from app.modules.social import (
    ReportStatus,
    Hashtag,
    BusinessTransaction,
    Vote,
    Report,
    Follow,
    ExpertiseBadge,
    ImpactCertificate,
    CulturalDictionaryEntry,
)

from app.modules.fact_checking import (
    FactCheckStatus,
    Fact,
    FactVerification,
    FactCorrection,
    CredibilityBadge,
    FactVote,
    MisinformationWarning,
)

from app.modules.wellness import (
    DigitalWellnessMetrics,
    WellnessAlert,
    WellnessSession,
    WellnessGoal,
    WellnessMode,
    WellnessLevel,
    UsagePattern,
)

from app.modules.marketplace import (
    ContentListing,
    ContentPurchase,
    ContentSubscription,
    ContentReview,
)

from app.modules.learning import (
    LearningPath,
    LearningModule,
    LearningEnrollment,
    Certificate,
)

from app.modules.local_economy import (
    LocalMarketListing,
    LocalMarketInquiry,
    LocalMarketTransaction,
    DigitalCooperative,
    CooperativeMember,
    CooperativeTransaction,
)

from app.modules.collaboration import (
    CollaborativeProject,
    ProjectContribution,
    ProjectStatus,
)

__all__ = [
    "Base",  # 2. التعديل الجوهري: تصدير Base ليراه Alembic
    "post_mentions",
    "user_hashtag_follows",
    "community_tags",
    "sticker_category_association",
    "post_hashtags",
    "UserType",
    "VerificationStatus",
    "PrivacyLevel",
    "UserRole",
    "User",
    "TokenBlacklist",
    "UserActivity",
    "UserEvent",
    "UserSession",
    "UserStatistics",
    "CommunityRole",
    "CommunityCategory",
    "Community",
    "CommunityMember",
    "CommunityStatistics",
    "CommunityRule",
    "CommunityInvitation",
    "Category",
    "SearchSuggestion",
    "SearchStatistics",
    "Tag",
    "Reel",
    "Article",
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
    "LivingTestimony",
    "NotificationStatus",
    "NotificationPriority",
    "NotificationCategory",
    "NotificationType",
    "NotificationPreferences",
    "NotificationGroup",
    "Notification",
    "NotificationDeliveryAttempt",
    "NotificationAnalytics",
    "NotificationDeliveryLog",
    "CallType",
    "CallStatus",
    "MessageType",
    "ScreenShareStatus",
    "ConversationType",
    "ConversationMemberRole",
    "Conversation",
    "ConversationMember",
    "Message",
    "MessageAttachment",
    "EncryptedSession",
    "EncryptedCall",
    "Call",
    "ScreenShareSession",
    "ConversationStatistics",
    "TicketStatus",
    "SupportTicket",
    "TicketResponse",
    "StickerPack",
    "Sticker",
    "StickerCategory",
    "StickerReport",
    "BlockDuration",
    "BlockType",
    "AppealStatus",
    "UserWarning",
    "UserBan",
    "IPBan",
    "BannedWord",
    "BanStatistics",
    "BanReason",
    "Block",
    "BlockLog",
    "BlockAppeal",
    "AmenhotepMessage",
    "AmenhotepChatAnalytics",
    "CommentEditHistory",
    "ReportStatus",
    "Hashtag",
    "BusinessTransaction",
    "Vote",
    "Report",
    "Follow",
    "ExpertiseBadge",
    "FactCheckStatus",
    "Fact",
    "FactVerification",
    "FactCorrection",
    "CredibilityBadge",
    "FactVote",
    "MisinformationWarning",
    "DigitalWellnessMetrics",
    "WellnessAlert",
    "WellnessSession",
    "WellnessGoal",
    "WellnessMode",
    "WellnessLevel",
    "UsagePattern",
    "ContentListing",
    "ContentPurchase",
    "ContentSubscription",
    "ContentReview",
    "LearningPath",
    "LearningModule",
    "LearningEnrollment",
    "Certificate",
    "LocalMarketListing",
    "LocalMarketInquiry",
    "LocalMarketTransaction",
    "DigitalCooperative",
    "CooperativeMember",
    "CooperativeTransaction",
    "CollaborativeProject",
    "ProjectContribution",
    "ProjectStatus",
    "ImpactCertificate",
    "CulturalDictionaryEntry",
]
