from tests.conftest import issue_token


def test_search_matches_by_name(client):
    token = issue_token(1, "Michael Brandt")
    resp = client.get(f"/r/{token}/contacts/search", params={"q": "anna"})
    assert resp.status_code == 200
    names = [c["name"] for c in resp.json()["results"]]
    assert any("Anna Schmidt" in n for n in names)


def test_search_empty_query_returns_no_results(client):
    token = issue_token(1, "Michael Brandt")
    resp = client.get(f"/r/{token}/contacts/search", params={"q": ""})
    assert resp.status_code == 200
    assert resp.json()["results"] == []


def test_search_rejects_invalid_token(client):
    resp = client.get("/r/does-not-exist/contacts/search", params={"q": "anna"})
    assert resp.status_code == 404
