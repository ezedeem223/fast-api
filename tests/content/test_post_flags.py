"""Test module for test post flags."""
def test_create_encrypted_living_testimony_post(authorized_client):
    """Test case for test create encrypted living testimony post."""
    payload = {
        "title": "Encrypted Memory",
        "content": "Secure content",
        "is_encrypted": True,
        "encryption_key_id": "key-xyz",
        "is_living_testimony": True,
    }
    res = authorized_client.post("/posts/", json=payload)
    assert res.status_code == 201
    post_data = res.json()
    assert post_data["is_encrypted"] is True
    assert post_data["encryption_key_id"] == "key-xyz"
    assert post_data["is_living_testimony"] is True
    assert post_data["living_testimony"] is not None
