def test_impact_certificates_and_cultural_entries(authorized_client):
    cert_res = authorized_client.post(
        "/impact/certificates",
        json={
            "title": "Clean Water",
            "description": "Provided clean water to 50 families",
            "impact_metrics": {"families": 50},
        },
    )
    assert cert_res.status_code == 201
    cert = cert_res.json()
    assert cert["title"] == "Clean Water"

    list_res = authorized_client.get("/impact/certificates")
    assert list_res.status_code == 200
    assert any(c["id"] == cert["id"] for c in list_res.json())

    entry_res = authorized_client.post(
        "/impact/cultural-dictionary",
        json={
            "term": "Majlis",
            "definition": "A gathering place",
            "cultural_context": "Used in Gulf countries",
            "language": "ar",
        },
    )
    assert entry_res.status_code == 201
    entry = entry_res.json()
    assert entry["term"] == "Majlis"

    search_res = authorized_client.get("/impact/cultural-dictionary", params={"q": "Maj"})
    assert search_res.status_code == 200
    assert any(e["id"] == entry["id"] for e in search_res.json())
