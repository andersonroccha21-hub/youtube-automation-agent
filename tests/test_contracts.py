from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from pipeline.config import load_config
from pipeline.models import Research, ScriptOutput, Source, Title, VisualOutput
from pipeline.orchestrator import Orchestrator
from pipeline.preflight import check
from pipeline.registry import SKILLS
from pipeline.skill import Context
from pipeline.storage import artifact, inside, read_json


def approved_thumbnail_output(config):
    from pipeline.approvals import PendingApproval

    run = Orchestrator.create(config, demo=True)
    with pytest.raises(PendingApproval):
        run.run()
    run.decide("pesquisa_titulos", "reviewer", True, "t1")
    with pytest.raises(PendingApproval):
        run.run()
    output = read_json(run.checkpoint_path("thumbnail"))
    output["thumbnail"]["selected_id"] = "thumb1"
    return run, output


def test_yaml_paths_are_relative_to_config(tmp_path):
    source = Path(__file__).parents[1] / "channels/canal_exemplo/config.yaml"
    payload = yaml.safe_load(source.read_text())
    payload["media"] = {
        "provider": "library",
        "library": [
            {
                "path": "assets/clip.mp4",
                "tags": ["clip"],
                "license": "owned",
                "source": "original",
            }
        ],
    }
    payload["narration"] = {"provider": "files", "files": {"hook": "assets/voice.wav"}}
    path = tmp_path / "new_channel" / "config.yaml"
    path.parent.mkdir()
    path.write_text(yaml.safe_dump(payload))
    config = load_config(path)
    assert config.media.library[0].path == path.parent / "assets/clip.mp4"
    assert config.narration.files["hook"] == path.parent / "assets/voice.wav"
    assert config.output_root == (path.parent / "../../runs").resolve()
    payload["typo"] = True
    path.write_text(yaml.safe_dump(payload))
    with pytest.raises(ValidationError, match="Extra inputs"):
        load_config(path)


def test_source_references_and_identifiers():
    source = Source(id="one", title="Source", url="https://example.org", excerpt="Evidence")
    title = Title(id="t1", title="Title", angle="Angle", rationale="Reason", source_ids=["unknown"])
    with pytest.raises(ValidationError, match="unknown research sources"):
        Research(summary="Summary", sources=[source], candidates=[title])
    with pytest.raises(ValidationError):
        Title(id="../escape", title="Title", angle="Angle", rationale="Reason", source_ids=["one"])


def test_contracts_reject_changed_title_and_missing_visual_coverage(config):
    run, payload = approved_thumbnail_output(config)
    previous = SKILLS["roteiro"].input_model.model_validate(payload)
    output = SKILLS["roteiro"](previous, Context(config, run.root, demo=True))
    changed = output.model_dump(mode="json")
    changed["script"]["title"] = "Another title"
    with pytest.raises(ValidationError, match="approved title"):
        ScriptOutput.model_validate(changed)
    visual = SKILLS["plano_visual"](output, Context(config, run.root, demo=True))
    changed = visual.model_dump(mode="json")
    changed["visual_plan"]["scenes"] = changed["visual_plan"]["scenes"][:1]
    with pytest.raises(ValidationError, match="every script section"):
        VisualOutput.model_validate(changed)


def test_artifact_path_cannot_escape(tmp_path):
    with pytest.raises(ValueError, match="escapes"):
        inside(tmp_path, "../outside")
    path = tmp_path / "empty"
    path.touch()
    with pytest.raises(ValueError, match="Empty"):
        artifact(tmp_path, path, "text")


def test_preflight_does_not_accept_missing_evidence(config, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "unit-test-key")
    with pytest.raises(ValueError, match="real research.sources"):
        check(config)
    check(config, demo=True)


def test_exported_schemas_match_runtime():
    from pipeline.config import Config

    root = Path(__file__).parents[1] / "schemas"
    assert read_json(root / "config.schema.json") == Config.model_json_schema()
    for name, skill in SKILLS.items():
        assert read_json(root / name / "input.schema.json") == skill.input_model.model_json_schema()
        assert (
            read_json(root / name / "output.schema.json") == skill.output_model.model_json_schema()
        )
