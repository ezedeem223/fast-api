"""Test module for test group messaging."""
def test_create_group_conversation(authorized_client, test_user2):
    """Test case for test create group conversation."""
    payload = {"title": "Project Alpha", "member_ids": [test_user2["id"]]}
    response = authorized_client.post("/message/conversations", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == payload["title"]
    assert len(data["members"]) == 2


def test_group_message_flow(authorized_client, test_user2):
    """Test case for test group message flow."""
    conversation_resp = authorized_client.post(
        "/message/conversations",
        json={"title": "Chat", "member_ids": [test_user2["id"]]},
    )
    assert conversation_resp.status_code == 201
    conversation_id = conversation_resp.json()["id"]

    send_resp = authorized_client.post(
        f"/message/conversations/{conversation_id}/messages",
        json={"content": "Hello group!"},
    )
    assert send_resp.status_code == 201

    list_resp = authorized_client.get(
        f"/message/conversations/{conversation_id}/messages"
    )
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1
    assert list_resp.json()[0]["content"] == "Hello group!"
