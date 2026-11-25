"""Export the actual runtime contracts for external skill integrations."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.config import Config  # noqa: E402
from pipeline.registry import SKILLS  # noqa: E402
from pipeline.storage import write_json  # noqa: E402


def main():
    root = Path(__file__).resolve().parents[1] / "schemas"
    write_json(root / "config.schema.json", Config.model_json_schema())
    for name, skill in SKILLS.items():
        write_json(root / name / "input.schema.json", skill.input_model.model_json_schema())
        write_json(root / name / "output.schema.json", skill.output_model.model_json_schema())
    print(root)


if __name__ == "__main__":
    main()
