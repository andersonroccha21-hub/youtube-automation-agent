import shutil

from pipeline.models import NarrationOutput, VisualOutput
from pipeline.providers.media import demo_audio, duration
from pipeline.skill import Context, Skill
from pipeline.storage import artifact


class Narracao(Skill):
    name = "narracao"
    input_model = VisualOutput
    output_model = NarrationOutput

    def execute(self, previous: VisualOutput, context: Context) -> dict:
        cfg = context.config
        segments = []
        for section in previous.script.sections:
            target = context.path(f"assets/narracao/{section.id}.wav")
            if context.demo:
                demo_audio(target)
            elif cfg.narration.provider == "files":
                source = cfg.narration.files.get(section.id)
                if source is None or not source.is_file():
                    raise ValueError(
                        f"Provide narration.files.{section.id} or use narration.provider=api"
                    )
                shutil.copyfile(source, target)
            else:
                context.speech.generate(section.narration, target)
            segments.append(
                {
                    "section_id": section.id,
                    "audio": artifact(context.root, target, "audio").model_dump(),
                    "duration_seconds": duration(target, cfg.editing),
                }
            )
        return {**previous.model_dump(mode="json"), "narration": {"segments": segments}}
