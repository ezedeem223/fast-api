from app import models
from app.services.users.service import UserService


def test_list_and_revoke_sessions(session, test_user):
    s1 = models.UserSession(
        user_id=test_user["id"],
        session_id="sess-1",
        ip_address="1.1.1.1",
        user_agent="agent1",
    )
    s2 = models.UserSession(
        user_id=test_user["id"],
        session_id="sess-2",
        ip_address="2.2.2.2",
        user_agent="agent2",
    )
    session.add_all([s1, s2])
    session.commit()

    service = UserService(session)
    current_user = session.get(models.User, test_user["id"])
    sessions = service.list_sessions(current_user)
    assert len(sessions) == 2

    result = service.revoke_session(current_user, "sess-1")
    assert "revoked" in result["message"]

    remaining = (
        session.query(models.UserSession).filter_by(user_id=test_user["id"]).all()
    )
    assert len(remaining) == 1
    assert remaining[0].session_id == "sess-2"

    blacklist = session.query(models.TokenBlacklist).filter_by(token="sess-1").first()
    assert blacklist is not None
