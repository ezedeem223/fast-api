"""Test module for shim export coverage."""

from app import moderation as moderation_module
from app.modules.moderation import service as moderation_service
from app.modules.posts import service as posts_service
from app.modules.users import service as users_service
from app.services.posts.vote_service import VoteService
from app.services.users.service import UserService


def test_moderation_shim_exports():
    """Ensure moderation shim re-exports the expected callables."""
    assert moderation_module.ban_user is moderation_service.ban_user
    assert moderation_module.calculate_ban_duration is moderation_service.calculate_ban_duration
    assert moderation_module.check_auto_ban is moderation_service.check_auto_ban
    assert moderation_module.process_report is moderation_service.process_report
    assert moderation_module.warn_user is moderation_service.warn_user
    assert set(moderation_module.__all__) == {
        "ban_user",
        "calculate_ban_duration",
        "check_auto_ban",
        "process_report",
        "warn_user",
    }


def test_posts_service_shim_exports():
    """Ensure posts module shim exposes VoteService."""
    assert posts_service.VoteService is VoteService
    assert posts_service.__all__ == ["VoteService"]


def test_users_service_shim_exports():
    """Ensure users module shim exposes UserService."""
    assert users_service.UserService is UserService
    assert users_service.__all__ == ["UserService"]
