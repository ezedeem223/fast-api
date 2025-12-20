


def test_user_media_listing(authorized_client, test_user, test_post):
    res = authorized_client.get(f"/users/profile/{test_user['id']}/media")
    assert res.status_code == 200
    payload = res.json()
    assert isinstance(payload, list)
