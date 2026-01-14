"""Test module for test support status routes."""
from types import SimpleNamespace

import pytest

from app import models, oauth2
from app.main import app


@pytest.fixture
def staff_client(authorized_client, test_user):
    """Pytest fixture for staff_client."""
    staff_user = SimpleNamespace(**test_user, is_admin=True, is_moderator=True)
    app.dependency_overrides[oauth2.get_current_user] = lambda: staff_user
    yield authorized_client
    app.dependency_overrides.pop(oauth2.get_current_user, None)


def _make_ticket(session, user_id):
    """Helper for  make ticket."""
    ticket = models.SupportTicket(
        user_id=user_id,
        subject="Help",
        description="Need assistance",
        status="open",
    )
    session.add(ticket)
    session.commit()
    session.refresh(ticket)
    return ticket


def test_support_ticket_status_requires_staff(authorized_client, session, test_user):
    """Test case for test support ticket status requires staff."""
    ticket = _make_ticket(session, test_user["id"])
    res = authorized_client.put(
        f"/support/tickets/{ticket.id}/status", json={"status": "closed"}
    )
    assert res.status_code == 403
    assert res.json()["detail"] == "Not authorized"


def test_support_ticket_status_update(staff_client, session, test_user):
    """Test case for test support ticket status update."""
    ticket = _make_ticket(session, test_user["id"])
    res = staff_client.put(
        f"/support/tickets/{ticket.id}/status", json={"status": "closed"}
    )
    assert res.status_code == 200
    assert res.json()["status"] == "closed"
