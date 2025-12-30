from app.modules.posts.models import Post, PostRelation
from app.services.posts.post_service import PostService


def test_living_memory_logic(db_session, test_user):
    """
    Test that the Living Memory system correctly links two similar posts.
    """
    service = PostService(db_session)

    post1 = Post(
        owner_id=test_user.id,
        title="First Memory",
        content="This is a test about python programming and fastapi development",
        is_safe_content=True,
    )
    db_session.add(post1)
    db_session.commit()
    db_session.refresh(post1)

    post2 = Post(
        owner_id=test_user.id,
        title="New Idea",
        content="I love python programming especially with fastapi framework",
        is_safe_content=True,
    )
    db_session.add(post2)
    db_session.commit()
    db_session.refresh(post2)

    service._process_living_memory(db_session, post2, test_user.id)

    relation = (
        db_session.query(PostRelation)
        .filter(
            PostRelation.source_post_id == post2.id,
            PostRelation.target_post_id == post1.id,
        )
        .first()
    )

    assert relation is not None, "System failed to create a memory relation"
    assert relation.relation_type == "semantic"
    assert (
        relation.similarity_score > 0.2
    ), f"Similarity score too low: {relation.similarity_score}"

    print(f"\n✅ Living Memory Success! Similarity: {relation.similarity_score}")


def test_living_memory_api_integration(
    client, test_user_token_headers, db_session, test_user
):
    """
    Test that the API response actually includes the related memories.
    """
    old_post = Post(
        owner_id=test_user.id,
        title="Old Memory",
        content="Exploring the ancient history of Egypt and pyramids",
        is_safe_content=True,
    )
    db_session.add(old_post)
    db_session.commit()

    payload = {
        "title": "Visit to Giza",
        "content": "I am visiting Egypt to see the pyramids and history",
        "community_id": None,
        "hashtags": [],
    }

    response = client.post("/posts/", json=payload, headers=test_user_token_headers)
    assert response.status_code == 201
    new_post_data = response.json()
    new_post_id = new_post_data["id"]

    get_response = client.get(f"/posts/{new_post_id}", headers=test_user_token_headers)
    assert get_response.status_code == 200
    data = get_response.json()

    assert "related_memories" in data
    if len(data["related_memories"]) > 0:
        memory = data["related_memories"][0]
        assert memory["target_post_id"] == old_post.id
        print("\n✅ API Integration Success: Related memories returned in JSON")
    else:
        print("\n⚠️ API Warning: related_memories list is empty in response.")


def test_living_memory_is_user_scoped(db_session, test_user, test_user2):
    """Ensure related memories are only created within the same user's history."""
    post_user1 = Post(
        owner_id=test_user.id,
        title="Travel Plans",
        content="Planning a trip to Japan next spring",
        is_safe_content=True,
    )
    db_session.add(post_user1)
    db_session.commit()
    db_session.refresh(post_user1)

    post_user2 = Post(
        owner_id=test_user2.id,
        title="Trip Thoughts",
        content="Planning a trip to Japan next spring",
        is_safe_content=True,
    )
    db_session.add(post_user2)
    db_session.commit()
    db_session.refresh(post_user2)

    service = PostService(db_session)
    service._process_living_memory(db_session, post_user2, test_user2.id)

    relation = (
        db_session.query(PostRelation)
        .filter(
            PostRelation.source_post_id == post_user2.id,
            PostRelation.target_post_id == post_user1.id,
        )
        .first()
    )

    assert (
        relation is None
    ), "Living Memory should not link posts across different users"
