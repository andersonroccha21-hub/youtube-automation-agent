from pathlib import Path

import pytest

from pipeline.config import load_config


@pytest.fixture
def config(tmp_path):
    cfg = load_config(Path(__file__).parents[1] / "channels/canal_exemplo/config.yaml")
    cfg.output_root = tmp_path / "runs"
    cfg.approvals.mode = "file"
    cfg.editing.width = 320
    cfg.editing.height = 180
    cfg.editing.fps = 12
    cfg.editing.preset = "ultrafast"
    return cfg
