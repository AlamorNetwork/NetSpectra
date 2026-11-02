"""Panel authentication, constrained configuration and actual asynchronous runs."""

import asyncio
import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pprl_core import cli, panel

HEADERS = {"X-NetSpectra-Client": "panel"}


@pytest.fixture
def setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path / "store"
    credentials = tmp_path / "access.json"
    panel.initialize(root, credentials)
    monkeypatch.setattr(
        cli, "_source_metadata", lambda: {"git_sha": "a" * 40, "dirty": False}
    )
    app = panel.create_app(root)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        yield client, json.loads(credentials.read_text()), root


def login(client: TestClient, credentials: dict):
    return client.post("/api/login", json=credentials, headers=HEADERS)


def wait_job(client: TestClient, job_id: str) -> dict:
    end = time.monotonic() + 20
    while time.monotonic() < end:
        state = client.get("/api/state").json()
        job = next(item for item in state["jobs"] if item["job_id"] == job_id)
        if job["status"] not in {"running", "cancelling"}:
            return job
        time.sleep(0.05)
    pytest.fail("panel job did not finish")


def test_authentication_and_secret_storage(setup):
    client, credentials, root = setup
    assert credentials["password"] not in (root / "panel-auth.json").read_text()
    assert client.get("/api/state").status_code == 401
    assert client.get("/api/session").json() == {"authenticated": False}
    assert login(client, credentials).status_code == 200
    assert client.get("/api/session").json() == {"authenticated": True}
    assert client.get("/api/state").json()["stats"]["runs"] == 0
    assert client.post("/api/logout", json={}, headers=HEADERS).status_code == 200
    assert client.get("/api/state").status_code == 401


def test_wrong_password_and_rate_limit(setup):
    client, credentials, _ = setup
    for _ in range(5):
        response = login(client, credentials | {"password": "incorrect"})
        assert response.status_code == 401
        assert credentials["password"] not in response.text
    assert login(client, credentials).status_code == 429


def test_cross_origin_and_invalid_host_are_rejected(setup):
    client, credentials, _ = setup
    assert client.post("/api/login", json=credentials).status_code == 403
    assert (
        client.post(
            "/api/login",
            json=credentials,
            headers=HEADERS | {"Origin": "https://untrusted.example"},
        ).status_code
        == 403
    )
    assert client.get("/", headers={"Host": "untrusted.example"}).status_code == 400


def test_static_page_has_local_assets_and_security_headers(setup):
    client, _, _ = setup
    response = client.get("/")
    assert response.status_code == 200
    assert 'lang="fa" dir="rtl"' in response.text
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert response.headers["cache-control"] == "no-store"
    for path in ["app.js", "style.css", "icons.svg", "fonts/Vazirmatn.woff2"]:
        assert client.get("/assets/" + path).status_code == 200
    assert client.get("/assets/../../panel-auth.json").status_code != 200


@pytest.mark.parametrize("protocol", ["tcp", "udp"])
def test_create_run_inspect_and_replay_through_api(setup, protocol: str):
    client, credentials, _ = setup
    assert login(client, credentials).status_code == 200
    body = {
        "name": "آزمایش واقعی " + protocol,
        "protocol": protocol,
        "run_seed": 42,
        "repetitions": 1,
        "execution": {
            "timeout": 15,
            "retries": 0,
            "attempt_timeout": 5,
            "retry_delay": 0,
        },
    }
    response = client.post("/api/experiments", json=body, headers=HEADERS)
    assert response.status_code == 201
    experiment = response.json()
    assert experiment["scenario"] == "seeded_echo"
    response = client.post(
        f"/api/experiments/{experiment['experiment_id']}/run",
        json=body["execution"],
        headers=HEADERS,
    )
    assert response.status_code == 202
    job = wait_job(client, response.json()["job_id"])
    assert job["status"] == "succeeded"
    details = client.get(f"/api/runs/{job['run_id']}").json()
    assert details["record"]["sample_size"] == 1
    assert details["record"]["metrics"][0]["value"] == 489
    replay = client.post(f"/api/runs/{job['run_id']}/replay", json={}, headers=HEADERS)
    assert replay.status_code == 202
    repeated = wait_job(client, replay.json()["job_id"])
    assert repeated["status"] == "succeeded"
    again = client.get(f"/api/runs/{repeated['run_id']}").json()
    assert again["summary"]["workload_sha256"] == details["summary"]["workload_sha256"]


def test_panel_cancel_cooperatively_reaps_running_work(setup, monkeypatch):
    client, credentials, _ = setup
    login(client, credentials)

    async def stall(*args, **kwargs):
        await asyncio.Event().wait()

    monkeypatch.setattr(cli, "probe_process_pair", stall)
    experiment = client.post(
        "/api/experiments", json={"name": "توقف"}, headers=HEADERS
    ).json()
    path = f"/api/experiments/{experiment['experiment_id']}/run"
    response = client.post(path, json={"timeout": 20}, headers=HEADERS)
    assert response.status_code == 202
    assert client.post(path, json={}, headers=HEADERS).status_code == 409
    job_id = response.json()["job_id"]
    assert (
        client.post(f"/api/jobs/{job_id}/cancel", json={}, headers=HEADERS).status_code
        == 200
    )
    job = wait_job(client, job_id)
    assert job["status"] == "cancelled"
    assert (
        client.get(f"/api/runs/{job['run_id']}").json()["record"]["failure_reason"]
        == "cancelled"
    )


def test_invalid_configuration_has_no_side_effects(setup):
    client, credentials, _ = setup
    login(client, credentials)
    for body in [
        {"name": " "},
        {"name": "x", "protocol": "https"},
        {"name": "x", "repetitions": 999},
        {"name": "x", "run_seed": True},
        {"name": "x", "destination": "uncontrolled.example"},
    ]:
        assert (
            client.post("/api/experiments", json=body, headers=HEADERS).status_code
            == 422
        )
    assert client.get("/api/state").json()["experiments"] == []


def test_stale_running_job_is_not_resumed(setup):
    _, _, root = setup
    job_id = "job-" + "b" * 32
    cli._atomic_write(
        root / "panel-jobs" / (job_id + ".json"),
        {"job_id": job_id, "status": "running", "started_at": cli._now()},
    )
    controller = panel.Controller(root)
    try:
        assert controller.jobs[job_id]["status"] == "interrupted"
        assert controller.active is None
    finally:
        controller.close()
