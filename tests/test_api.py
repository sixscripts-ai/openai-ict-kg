from fastapi.testclient import TestClient

from ict_kg.api import app


def _token(client: TestClient, tenant_id: str = "t1", role: str = "admin") -> str:
    response = client.post("/auth/token", json={"subject": "tester", "tenant_id": tenant_id, "role": role})
    assert response.status_code == 200
    return response.json()["access_token"]


def test_end_to_end_graph_flow() -> None:
    client = TestClient(app)
    token = _token(client, "t1", "admin")
    headers = {"Authorization": f"Bearer {token}"}

    assert client.get("/ready").status_code == 200

    n1 = client.post(
        "/nodes",
        json={"tenant_id": "t1", "title": "Liquidity Sweep", "content": "Price sweeps highs before reversal.", "domain": "ict", "metadata": {"source": "journal"}},
        headers=headers,
    )
    assert n1.status_code == 200
    node1_id = n1.json()["id"]

    n2 = client.post(
        "/nodes",
        json={"tenant_id": "t1", "title": "Order Block", "content": "Last up-close/down-close candle before move.", "domain": "trading", "metadata": {}},
        headers=headers,
    )
    assert n2.status_code == 200
    node2_id = n2.json()["id"]

    n3 = client.post(
        "/nodes",
        json={"tenant_id": "t1", "title": "Displacement", "content": "Strong expansion candle confirms intent.", "domain": "ict", "metadata": {}},
        headers=headers,
    )
    assert n3.status_code == 200

    assert client.post(
        "/edges",
        json={"tenant_id": "t1", "source_node_id": node1_id, "target_node_id": node2_id, "relation_type": "related_to", "weight": 0.8},
        headers=headers,
    ).status_code == 200

    assert client.post(
        "/edges",
        json={"tenant_id": "t1", "source_node_id": node2_id, "target_node_id": n3.json()["id"], "relation_type": "depends_on", "weight": 0.9},
        headers=headers,
    ).status_code == 200

    assert client.post(
        "/memories",
        json={"tenant_id": "t1", "title": "London note", "content": "Wait for sweep and displacement.", "domain": "memory", "metadata": {"day": "monday"}},
        headers=headers,
    ).status_code == 200

    q = client.post(
        "/query",
        json={"tenant_id": "t1", "text": "sweep entry", "top_k": 3, "include": "all", "rerank": True},
        headers=headers,
    )
    assert q.status_code == 200
    assert q.json()["results"][0]["explanation"]

    neighbors = client.get(
        f"/nodes/{node1_id}/neighbors",
        params={"depth": 2, "relation_type": "related_to", "limit": 10},
        headers=headers,
    )
    assert neighbors.status_code == 200

    assert client.get(
        "/paths",
        params={"from_node_id": node1_id, "to_node_id": n3.json()["id"], "max_hops": 3},
        headers=headers,
    ).status_code == 200

    multi = client.get(
        "/paths/multi",
        params={"from_node_id": node1_id, "to_node_id": n3.json()["id"], "k": 2, "max_hops": 4},
        headers=headers,
    )
    assert multi.status_code == 200

    metrics = client.get("/metrics", headers=headers)
    assert metrics.status_code == 200
    assert metrics.json().get("queries", 0) >= 1


def test_role_and_job_endpoints() -> None:
    client = TestClient(app)
    writer = _token(client, "t2", "writer")
    reader = _token(client, "t2", "reader")
    writer_h = {"Authorization": f"Bearer {writer}"}
    reader_h = {"Authorization": f"Bearer {reader}"}

    create_as_reader = client.post(
        "/nodes",
        json={"tenant_id": "t2", "title": "X", "content": "Y", "metadata": {}},
        headers=reader_h,
    )
    assert create_as_reader.status_code == 403

    job = client.post(
        "/ingest/jobs",
        json={"tenant_id": "t2", "source_system": "web", "source": "https://example.com", "domain": "knowledge-base"},
        headers=writer_h,
    )
    assert job.status_code == 200
    job_id = job.json()["id"]

    get_job = client.get(f"/ingest/jobs/{job_id}", headers=reader_h)
    assert get_job.status_code == 200

    list_jobs = client.get("/ingest/jobs", params={"limit": 10, "offset": 0}, headers=reader_h)
    assert list_jobs.status_code == 200
    assert list_jobs.json()["total"] >= 1

    cancel = client.post(f"/ingest/jobs/{job_id}/cancel", headers=writer_h)
    assert cancel.status_code in (200, 409)

    forbidden_metrics = client.get("/metrics", headers=reader_h)
    assert forbidden_metrics.status_code == 403
