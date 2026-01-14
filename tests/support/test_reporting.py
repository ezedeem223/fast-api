"""Test module for test reporting."""
from app import models


def test_report_post(authorized_client, test_post, session):
    """Test case for test report post."""
    report_data = {"post_id": test_post["id"], "reason": "Inappropriate content"}
    response = authorized_client.post("/report/", json=report_data)
    assert response.status_code == 201
    assert response.json()["message"] == "Report submitted successfully"

    report = session.query(models.Report).filter_by(post_id=test_post["id"]).first()
    assert report is not None
    assert report.reason == "Inappropriate content"


def test_report_comment(authorized_client, test_comment, session):
    """Test case for test report comment."""
    report_data = {"comment_id": test_comment["id"], "reason": "Spam"}
    response = authorized_client.post("/report/", json=report_data)
    assert response.status_code == 201
    assert response.json()["message"] == "Report submitted successfully"

    report = (
        session.query(models.Report).filter_by(comment_id=test_comment["id"]).first()
    )
    assert report is not None
    assert report.reason == "Spam"


def test_report_nonexistent_post(authorized_client):
    """Test case for test report nonexistent post."""
    report_data = {"post_id": 9999, "reason": "Inappropriate content"}
    response = authorized_client.post("/report/", json=report_data)
    assert response.status_code == 404
    assert response.json()["detail"] == "Post not found"


def test_report_nonexistent_comment(authorized_client):
    """Test case for test report nonexistent comment."""
    report_data = {"comment_id": 9999, "reason": "Spam"}
    response = authorized_client.post("/report/", json=report_data)
    assert response.status_code == 404
    assert response.json()["detail"] == "Comment not found"
