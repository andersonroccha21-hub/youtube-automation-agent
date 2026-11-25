"""Common skill interface and its injected runtime context."""

from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

from pipeline.config import Config
from pipeline.models import Model
from pipeline.providers.api import ImageProvider, SpeechProvider, TextProvider
from pipeline.storage import verify_artifacts


@dataclass
class Context:
    config: Config
    root: Path
    demo: bool = False
    feedback: str = ""

    @property
    def text(self):
        return TextProvider(self.config)

    @property
    def image(self):
        return ImageProvider(self.config)

    @property
    def speech(self):
        return SpeechProvider(self.config)

    def path(self, relative: str) -> Path:
        from pipeline.storage import inside

        path = inside(self.root, relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path


class Skill:
    name: ClassVar[str]
    input_model: ClassVar[type[Model]]
    output_model: ClassVar[type[Model]]

    def __call__(self, previous: Model, context: Context) -> Model:
        previous = self.input_model.model_validate(previous.model_dump(mode="json"))
        verify_artifacts(context.root, previous)
        result = self.output_model.model_validate(self.execute(previous, context))
        before = previous.model_dump(mode="json")
        after = result.model_dump(mode="json")
        if any(after.get(key) != value for key, value in before.items()):
            raise ValueError(f"{self.name} modified upstream approved context")
        verify_artifacts(context.root, result)
        return result

    def execute(self, previous: Model, context: Context) -> dict:
        raise NotImplementedError
