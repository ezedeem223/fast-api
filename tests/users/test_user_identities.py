"""Test module for test user identities."""
def test_identity_crud_flow(authorized_client, test_user2):
    # link identity
    """Test case for test identity crud flow."""
    res = authorized_client.post(
        "/users/me/identities",
        json={"linked_user_id": test_user2["id"], "relationship_type": "alias"},
    )
    assert res.status_code == 201
    identity_id = res.json()["id"]

    # list identities
    list_res = authorized_client.get("/users/me/identities")
    assert list_res.status_code == 200
    assert any(item["id"] == identity_id for item in list_res.json())

    # remove identity
    delete_res = authorized_client.delete(f"/users/me/identities/{test_user2['id']}")
    assert delete_res.status_code == 204

    # ensure removed
    list_res = authorized_client.get("/users/me/identities")
    assert all(item["linked_user_id"] != test_user2["id"] for item in list_res.json())
