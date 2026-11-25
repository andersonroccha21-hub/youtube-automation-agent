import time

import pytest
import yaml
from fastapi.testclient import TestClient

from pipeline.approvals import PendingApproval
from pipeline.orchestrator import Orchestrator
from pipeline.storage import read_json, write_json
from web.app import create_app


@pytest.fixture
def dashboard(config, tmp_path):
    config.approvals.optional["roteiro"] = True
    channels = tmp_path / "channels"
    folder = channels / "example"
    folder.mkdir(parents=True)
    (folder / "config.yaml").write_text(yaml.safe_dump(config.model_dump(mode="json")))
    app = create_app(channels)
    with TestClient(app) as client:
        yield client, app, config, channels


def wait_for(client, path, status):
    deadline = time.monotonic() + 35
    while time.monotonic() < deadline:
        response = client.get(path)
        assert response.status_code == 200, response.text
        payload = response.json()
        if not payload["busy"] and payload["status"] == status:
            return payload
        if not payload["busy"] and payload["status"] in ("failed", "rejected"):
            pytest.fail(str(payload))
        time.sleep(0.03)
    pytest.fail(f"Run did not reach {status}")


def start(client, config):
    response = client.post(
        "/api/runs",
        json={"channel_id": config.channel.id, "topic": "Teste de produção web", "demo": True},
    )
    assert response.status_code == 202, response.text
    run_id = response.json()["id"]
    return f"/api/channels/{config.channel.id}/runs/{run_id}"


def decide(client, path, run, selected_id=None):
    return client.post(
        path + "/approve",
        json={
            "stage": run["current"],
            "reviewer": "Web test fixture",
            "selected_id": selected_id,
            "artifact_digest": run["review"]["artifact_digest"],
        },
    )


def test_channels_and_static_dashboard(dashboard, monkeypatch):
    client, app, config, channels = dashboard
    monkeypatch.setenv("OPENAI_API_KEY", "PRIVATE-KEY-DO-NOT-SEND")
    response = client.get("/api/channels")
    assert response.status_code == 200
    channel = response.json()["channels"][0]
    assert channel["id"] == config.channel.id
    assert channel["config_path"] == "example/config.yaml"
    assert not channel["production_ready"]
    assert "PRIVATE-KEY" not in response.text
    page = client.get("/")
    assert page.status_code == 200
    assert "Darklab Studio" in page.text
    assert client.get("/static/app.js").status_code == 200
    assert len(client.get("/static/styles.css").content) > 10000
    assert client.get("/api/channels/missing/runs").status_code == 404
    assert (
        client.post(
            "/api/runs", json={"channel_id": config.channel.id, "topic": "Production"}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/runs", json={"channel_id": config.channel.id, "topic": "   ", "demo": True}
        ).status_code
        == 422
    )


def test_api_full_pipeline_approvals_optional_gate_video_range_and_reload(dashboard):
    client, app, config, channels = dashboard
    path = start(client, config)
    titles = wait_for(client, path, "pending_approval")
    assert titles["current"] == "pesquisa_titulos"
    assert titles["progress"] == 0
    assert titles["stages"][0]["status"] == "pending_approval"
    assert titles["stages"][1]["status"] == "pending"
    assert client.post(path + "/resume").status_code == 409
    assert decide(client, path, titles, "nonexistent").status_code == 409
    assert decide(client, path, titles).status_code == 409
    assert decide(client, path, titles, "t2").status_code == 202
    thumbs = wait_for(client, path, "pending_approval")
    assert thumbs["current"] == "thumbnail"
    assert thumbs["progress"] == 14
    assert thumbs["stages"][0]["status"] == "completed"
    image = client.get(thumbs["review"]["candidates"][0]["image_url"])
    assert image.status_code == 200
    assert image.headers["content-type"].startswith("image/jpeg")
    assert client.get(path + "/checkpoints/roteiro").status_code == 404
    assert decide(client, path, thumbs, "thumb1").status_code == 202
    script = wait_for(client, path, "pending_approval")
    assert script["current"] == "roteiro"
    assert script["review"]["content"]["title"].startswith("DEMO 2:")
    assert client.get(path + "/checkpoints/plano_visual").status_code == 404
    assert decide(client, path, script).status_code == 202
    completed = wait_for(client, path, "completed")
    assert completed["progress"] == 100
    assert all(stage["status"] == "completed" for stage in completed["stages"])
    assert completed["video"]["demo"] is True
    video = client.get(completed["video"]["url"], headers={"Range": "bytes=0-100"})
    assert video.status_code == 206
    assert len(video.content) == 101
    assert video.headers["content-type"].startswith("video/mp4")
    assert client.get(path + "/media/state.json").status_code == 404
    assert client.get(path + "/media/..%2F..%2F.env").status_code == 404
    assert client.post(path + "/resume").status_code == 409
    with TestClient(create_app(channels)) as reloaded:
        persisted = reloaded.get(path).json()
        assert persisted["status"] == "completed"
        assert persisted["video"]["url"] == completed["video"]["url"]
        assert len(reloaded.get(f"/api/channels/{config.channel.id}/runs").json()["runs"]) == 1


def test_stale_review_and_modified_media_cannot_be_approved(dashboard):
    client, app, config, channels = dashboard
    path = start(client, config)
    titles = wait_for(client, path, "pending_approval")
    response = client.post(
        path + "/approve",
        json={
            "stage": "pesquisa_titulos",
            "reviewer": "Human",
            "selected_id": "t1",
            "artifact_digest": "f" * 64,
        },
    )
    assert response.status_code == 409
    assert "stale" in response.text
    assert decide(client, path, titles, "t1").status_code == 202
    thumbs = wait_for(client, path, "pending_approval")
    run_root = config.output_root / config.channel.id / thumbs["id"]
    payload = read_json(run_root / "checkpoints/thumbnail.json")
    relative = payload["thumbnail"]["candidates"][0]["image"]["path"]
    (run_root / relative).write_bytes(b"tampered")
    assert client.get(thumbs["review"]["candidates"][0]["image_url"]).status_code == 409
    assert decide(client, path, thumbs, "thumb1").status_code == 409
    assert "thumbnail" not in read_json(run_root / "state.json")["approvals"]


def test_revision_invalidates_downstream_and_requires_approval_again(dashboard):
    client, app, config, channels = dashboard
    path = start(client, config)
    titles = wait_for(client, path, "pending_approval")
    assert decide(client, path, titles, "t1").status_code == 202
    thumbs = wait_for(client, path, "pending_approval")
    response = client.post(
        path + "/revise", json={"stage": "pesquisa_titulos", "feedback": "Mude o ângulo"}
    )
    assert response.status_code == 202
    revised = wait_for(client, path, "pending_approval")
    assert revised["current"] == "pesquisa_titulos"
    assert revised["progress"] == 0
    assert client.get(path + "/checkpoints/thumbnail").status_code == 404
    root = config.output_root / config.channel.id / thumbs["id"]
    assert not read_json(root / "state.json")["approvals"]


def test_rejection_is_persisted_and_cannot_be_resumed_without_revision(dashboard):
    client, app, config, channels = dashboard
    path = start(client, config)
    titles = wait_for(client, path, "pending_approval")
    response = client.post(
        path + "/approve",
        json={
            "stage": titles["current"],
            "reviewer": "Human",
            "approve": False,
            "artifact_digest": titles["review"]["artifact_digest"],
            "feedback": "Refazer títulos",
        },
    )
    assert response.status_code == 202
    rejected = client.get(path).json()
    assert rejected["status"] == "rejected"
    assert rejected["stages"][0]["status"] == "rejected"
    assert client.post(path + "/resume").status_code == 409


def test_channel_discovery_invalid_duplicate_yml_and_external_symlink(dashboard, tmp_path):
    client, app, config, channels = dashboard
    invalid = channels / "invalid.yaml"
    invalid.write_text("not: a-channel-config")
    (channels / "broken.yaml").write_text("channel: [unterminated")
    other = config.model_copy(deep=True)
    other.channel.id = "different"
    other.channel.name = "Outro canal"
    (channels / "other.yml").write_text(yaml.safe_dump(other.model_dump(mode="json")))
    outside = tmp_path / "outside.yaml"
    outside.write_text(yaml.safe_dump(other.model_dump(mode="json")))
    (channels / "link.yaml").symlink_to(outside)
    payload = client.get("/api/channels").json()
    assert len(payload["channels"]) == 2
    assert len(payload["errors"]) == 3
    (channels / "duplicate.yaml").write_text(yaml.safe_dump(config.model_dump(mode="json")))
    payload = client.get("/api/channels").json()
    assert [c["id"] for c in payload["channels"]] == ["different"]
    assert any("duplicado" in error["error"] for error in payload["errors"])


def test_server_forces_noninteractive_without_changing_cli_config(dashboard, monkeypatch):
    client, app, config, channels = dashboard
    config.approvals.mode = "interactive"
    run = Orchestrator.create(config, demo=True)

    class TTY:
        @staticmethod
        def isatty():
            return True

    monkeypatch.setattr("pipeline.orchestrator.sys.stdin", TTY())
    monkeypatch.setattr(
        "builtins.input", lambda *args: pytest.fail("Web worker must not read stdin")
    )
    with pytest.raises(PendingApproval):
        run.run(interactive=False)
    assert run.state().config.approvals.mode == "interactive"
    assert (
        client.get(f"/api/channels/{config.channel.id}/runs/{run.root.name}").json()["status"]
        == "pending_approval"
    )


def test_interrupted_cli_run_is_visible_and_can_resume(dashboard):
    client, app, config, channels = dashboard
    run = Orchestrator.create(config, demo=True)
    state = run.state()
    state.status = "running"
    state.current = "pesquisa_titulos"
    write_json(run.state_path, state)
    path = f"/api/channels/{config.channel.id}/runs/{run.root.name}"
    assert client.get(path).json()["status"] == "interrupted"
    assert client.post(path + "/resume").status_code == 202
    assert wait_for(client, path, "pending_approval")["current"] == "pesquisa_titulos"


def test_busy_run_rejects_duplicate_actions_and_cross_origin(dashboard, monkeypatch):
    client, app, config, channels = dashboard
    path = start(client, config)
    titles = wait_for(client, path, "pending_approval")
    monkeypatch.setattr(app.state.runner, "busy", lambda run: True)
    assert decide(client, path, titles, "t1").status_code == 409
    blocked = client.post(
        "/api/runs",
        json={"channel_id": config.channel.id, "topic": "Bad", "demo": True},
        headers={"Origin": "https://foreign.example"},
    )
    assert blocked.status_code == 403
    assert client.get("/api/channels", headers={"Host": "foreign.example"}).status_code == 400
