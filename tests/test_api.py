from uuid import uuid4

from fastapi.testclient import TestClient

import app.main as main


client = TestClient(main.app)


def test_health_endpoint():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_ready_endpoint():
    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"


def test_api_info_endpoint():
    response = client.get("/api/v1/")

    assert response.status_code == 200
    assert response.json()["status"] == "running"


def test_unknown_job_returns_404():
    response = client.get("/api/v1/jobs/nonexistent-test-job")

    assert response.status_code == 404
    assert response.json()["code"] == "JOB_NOT_FOUND"
    assert response.json()["retryable"] is False
    assert response.json()["details"]["job_id"] == "nonexistent-test-job"


def test_create_job_returns_accepted_response(monkeypatch):
    # Prevent the test from launching a real video-generation job.
    monkeypatch.setattr(main, "enqueue_job", lambda job_id: None)

    response = client.post(
        "/api/v1/jobs",
        headers={"Idempotency-Key": f"test-{uuid4()}"},
        json={
            "script": "A cat is sleeping in the sunshine.",
            "aspect_ratio": "16:9",
            "narration_language": "en",
        },
    )

    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "queued"
    assert data["progress"] == 0
    assert data["job_id"]
    assert data["status_url"].startswith("/api/v1/jobs/")


def test_same_idempotency_key_returns_same_job(monkeypatch):
    monkeypatch.setattr(main, "enqueue_job", lambda job_id: None)

    key = f"idempotency-{uuid4()}"
    payload = {
        "script": "A small boat sails across the lake.",
        "aspect_ratio": "16:9",
        "narration_language": "en",
    }
    headers = {"Idempotency-Key": key}

    first = client.post("/api/v1/jobs", headers=headers, json=payload)
    second = client.post("/api/v1/jobs", headers=headers, json=payload)

    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["job_id"] == second.json()["job_id"]


def test_reusing_idempotency_key_with_different_payload_returns_409(
    monkeypatch,
):
    monkeypatch.setattr(main, "enqueue_job", lambda job_id: None)

    key = f"conflict-{uuid4()}"
    headers = {"Idempotency-Key": key}

    first = client.post(
        "/api/v1/jobs",
        headers=headers,
        json={
            "script": "A cat sleeps.",
            "aspect_ratio": "16:9",
            "narration_language": "en",
        },
    )

    second = client.post(
        "/api/v1/jobs",
        headers=headers,
        json={
            "script": "A dog runs.",
            "aspect_ratio": "16:9",
            "narration_language": "en",
        },
    )

    assert first.status_code == 202
    assert second.status_code == 409
    assert second.json()["code"] == "IDEMPOTENCY_CONFLICT"
    assert second.json()["retryable"] is False
    assert "message" in second.json()
    assert "details" in second.json()
    
def test_empty_script_is_rejected():
    response = client.post(
        "/api/v1/jobs",
        headers={"Idempotency-Key": f"empty-{uuid4()}"},
        json={
            "script": "",
            "aspect_ratio": "16:9",
            "narration_language": "en",
        },
    )

    assert response.status_code == 422


def test_missing_idempotency_key_is_rejected():
    response = client.post(
        "/api/v1/jobs",
        json={
            "script": "A river flows through a green valley.",
            "aspect_ratio": "16:9",
            "narration_language": "en",
        },
    )

    assert response.status_code == 422