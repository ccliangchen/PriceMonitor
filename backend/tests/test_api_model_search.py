def test_model_search_requires_logged_in_platform(client):
    response = client.post(
        "/api/v1/listings/search-model",
        json={
            "query": "iQOO Neo11 至尊版 12G+512G",
            "platform": "taobao",
        },
    )

    assert response.status_code == 409
    assert "淘宝" in response.json()["detail"]


def test_model_search_rejects_unknown_platform(client):
    response = client.post(
        "/api/v1/listings/search-model",
        json={"query": "iQOO Neo11 12G+512G", "platform": "pdd"},
    )

    assert response.status_code == 422
