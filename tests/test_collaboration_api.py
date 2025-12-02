def test_collaboration_project_crud(authorized_client, test_user):
    # Create project
    res = authorized_client.post(
        "/collaboration/projects",
        json={
            "title": "AI Lab",
            "description": "Build an open AI toolkit",
            "goals": "Ship MVP",
        },
    )
    assert res.status_code == 200
    project = res.json()
    assert project["title"] == "AI Lab"
    project_id = project["id"]

    # Add contribution
    contrib_res = authorized_client.post(
        f"/collaboration/projects/{project_id}/contributions",
        json={"content": "Wrote first draft", "contribution_type": "text"},
    )
    assert contrib_res.status_code == 201
    assert contrib_res.json()["project_id"] == project_id

    # Get project with contributions
    fetch_res = authorized_client.get(f"/collaboration/projects/{project_id}")
    assert fetch_res.status_code == 200
    data = fetch_res.json()
    assert data["id"] == project_id
    assert len(data["contributions"]) == 1

    # List contributions
    list_res = authorized_client.get(
        f"/collaboration/projects/{project_id}/contributions"
    )
    assert list_res.status_code == 200
    assert len(list_res.json()) == 1
