import json
import shutil

import pytest

from pipeline.approvals import PendingApproval, RejectedApproval
from pipeline.cli import main
from pipeline.models import STAGES
from pipeline.orchestrator import Orchestrator
from pipeline.providers.media import execute, probe
from pipeline.storage import digest, read_json, run_lock, write_json


def pause(run):
    with pytest.raises(PendingApproval):
        run.run()
    return run.state()


def approve_title(run):
    run.decide("pesquisa_titulos", "test-reviewer", True, "t2")


def test_required_approvals_cannot_be_disabled(config):
    config.approvals.optional = {"pesquisa_titulos": False, "thumbnail": False}
    run = Orchestrator.create(config, "A test topic", demo=True)
    assert pause(run).current == "pesquisa_titulos"
    assert not run.checkpoint_path("thumbnail").exists()
    with pytest.raises(ValueError, match="Select a candidate"):
        run.decide("pesquisa_titulos", "person", True)
    with pytest.raises(ValueError, match="does not exist"):
        run.decide("pesquisa_titulos", "person", True, "unknown")
    with pytest.raises(ValueError, match="pending"):
        run.decide("thumbnail", "person", True, "thumb1")
    approve_title(run)
    assert pause(run).current == "thumbnail"
    assert not run.checkpoint_path("roteiro").exists()


def test_rejection_and_revision_invalidate_dependents(config):
    run = Orchestrator.create(config, demo=True)
    pause(run)
    approve_title(run)
    pause(run)
    old = read_json(run.checkpoint_path("thumbnail"))
    run.decide("thumbnail", "reviewer", False, feedback="Try simpler imagery")
    with pytest.raises(RejectedApproval):
        run.run()
    run.revise("thumbnail", "Try simpler imagery")
    assert "pesquisa_titulos" in run.state().approvals
    assert "thumbnail" not in run.state().checkpoints
    assert "thumbnail" not in run.state().approvals
    pause(run)
    new = read_json(run.checkpoint_path("thumbnail"))
    assert (
        old["thumbnail"]["candidates"][0]["prompt"] != new["thumbnail"]["candidates"][0]["prompt"]
    )
    run.revise("pesquisa_titulos", "Different angle")
    assert not run.state().checkpoints
    assert not run.state().approvals


def test_checkpoint_and_asset_tampering_fail_closed(config):
    run = Orchestrator.create(config, demo=True)
    pause(run)
    approve_title(run)
    pause(run)
    thumbnail = read_json(run.checkpoint_path("thumbnail"))["thumbnail"]["candidates"][0]
    path = run.root / thumbnail["image"]["path"]
    path.write_bytes(b"modified")
    with pytest.raises(ValueError, match="modified artifact"):
        run.decide("thumbnail", "reviewer", True, "thumb1")
    with pytest.raises(ValueError, match="modified artifact"):
        run.run()
    run.revise("thumbnail", "Regenerate altered thumbnail")
    pause(run)
    payload = read_json(run.checkpoint_path("thumbnail"))
    payload["thumbnail"]["candidates"][0]["prompt"] = "tampered"
    write_json(run.checkpoint_path("thumbnail"), payload)
    with pytest.raises(ValueError, match="Checkpoint thumbnail changed"):
        run.run()


def test_approval_bound_to_checkpoint(config):
    run = Orchestrator.create(config, demo=True)
    pause(run)
    approve_title(run)
    payload = read_json(run.state_path)
    payload["approvals"]["pesquisa_titulos"]["artifact_digest"] = "wrong"
    write_json(run.state_path, payload)
    with pytest.raises(ValueError, match="different artifact"):
        run.run()


def test_resume_keeps_outputs_and_channels_isolated(config):
    run = Orchestrator.create(config, demo=True)
    pause(run)
    before = run.checkpoint_path("pesquisa_titulos").stat().st_mtime_ns
    pause(run)
    assert run.checkpoint_path("pesquisa_titulos").stat().st_mtime_ns == before
    other = config.model_copy(deep=True)
    other.channel.id = "different_channel"
    other.channel.language = "de-DE"
    other_run = Orchestrator.create(other, demo=True)
    assert other_run.root.parent != run.root.parent
    with pytest.raises(ValueError, match="another channel"):
        Orchestrator(other, run.root).run()
    changed = config.model_copy(deep=True)
    changed.channel.tone = "different tone"
    with pytest.raises(ValueError, match="config changed"):
        Orchestrator(changed, run.root).run()


def test_run_lock_prevents_concurrent_mutation(config):
    run = Orchestrator.create(config, demo=True)
    with run_lock(run.root):
        with pytest.raises(ValueError, match="Another process"):
            run.run()


def test_noninteractive_cli_pauses_and_explicit_review_resumes(tmp_path):
    import yaml

    from pipeline.config import load_config

    source = __import__("pathlib").Path(__file__).parents[1] / "channels/canal_exemplo/config.yaml"
    raw = yaml.safe_load(source.read_text())
    raw["output_root"] = str(tmp_path / "runs")
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(raw))
    assert main(["--channel", str(config_path), "--demo"]) == 2
    root = next((load_config(config_path).output_root / "canal_exemplo").iterdir())
    argv = ["--channel", str(config_path), "--run-dir", str(root)]
    assert (
        main([*argv, "--approve", "pesquisa_titulos", "--select", "t1", "--reviewer", "human"]) == 0
    )
    assert main(argv) == 2
    assert read_json(root / "state.json")["current"] == "thumbnail"
    assert main([*argv, "--topic", "changed"]) == 1
    assert main([*argv, "--status"]) == 0


@pytest.mark.skipif(
    not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="FFmpeg required"
)
def test_full_pipeline_real_mp4_and_optional_gate(config):
    config.approvals.optional["roteiro"] = True
    run = Orchestrator.create(config, "Deterministic integration test", demo=True)
    pause(run)
    approve_title(run)
    pause(run)
    run.decide("thumbnail", "reviewer", True, "thumb2")
    assert pause(run).current == "roteiro"
    assert not run.checkpoint_path("plano_visual").exists()
    run.decide("roteiro", "reviewer", True)
    result = run.run()
    assert run.state().status == "completed"
    assert tuple(run.state().checkpoints) == STAGES
    assert result.script.title == result.research.selected().title
    assert result.research.selected_id == "t2"
    assert result.thumbnail.selected_id == "thumb2"
    assert result.video.demo
    assert 2.8 <= result.video.duration_seconds <= 3.5
    path = run.root / result.video.file.path
    info = probe(path, config.editing)
    assert {s["codec_type"] for s in info["streams"]} == {"audio", "video"}
    execute([config.editing.ffmpeg, "-v", "error", "-i", str(path), "-f", "null", "-"], 30)
    original_mtime = path.stat().st_mtime_ns
    resumed = Orchestrator(config, run.root).run()
    assert digest(resumed) == digest(result)
    assert path.stat().st_mtime_ns == original_mtime
    assert json.loads((run.root / "result.json").read_text())["video"]["demo"] is True
