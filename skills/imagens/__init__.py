import re
import shutil

from PIL import Image

from pipeline.models import ImagesOutput, NarrationOutput
from pipeline.providers.media import demo_image, duration
from pipeline.skill import Context, Skill
from pipeline.storage import artifact

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm"}


def tokens(text):
    return set(re.findall(r"\w+", text.casefold()))


class Imagens(Skill):
    name = "imagens"
    input_model = NarrationOutput
    output_model = ImagesOutput

    def execute(self, previous: NarrationOutput, context: Context) -> dict:
        cfg = context.config
        assets = []
        for scene in previous.visual_plan.scenes:
            if context.demo:
                target = context.path(f"assets/imagens/{scene.id}.jpg")
                demo_image(target, scene.description, (cfg.editing.width, cfg.editing.height))
                provenance, license_name = "Synthetic demonstration fixture", "Demo only"
            elif cfg.media.provider == "library":
                query = tokens(" ".join(scene.search_terms))
                eligible = [
                    m
                    for m in cfg.media.library
                    if ("video" if m.path.suffix.lower() in VIDEO_EXTENSIONS else "image")
                    == scene.media_type
                ]
                ranked = sorted(
                    eligible, key=lambda m: len(tokens(" ".join(m.tags)) & query), reverse=True
                )
                if not ranked or not (tokens(" ".join(ranked[0].tags)) & query):
                    raise ValueError(
                        f"No tagged library match for scene {scene.id}: {scene.search_terms}"
                    )
                item = ranked[0]
                target = context.path(f"assets/imagens/{scene.id}{item.path.suffix.lower()}")
                shutil.copyfile(item.path, target)
                provenance, license_name = item.source, item.license
            else:
                if scene.media_type != "image":
                    raise ValueError(
                        "Generated media provider supports images; select B-roll from library"
                    )
                target = context.path(f"assets/imagens/{scene.id}.jpg")
                context.image.generate(
                    f"{scene.prompt}\nAesthetic: {cfg.channel.aesthetic}\n"
                    f"Rules: {'; '.join(cfg.channel.rules)}\n{cfg.prompts.get(self.name, '')}\n"
                    f"Revision: {context.feedback}",
                    target,
                    (cfg.editing.width, cfg.editing.height),
                )
                provenance = f"Generated using {cfg.image.model}"
                license_name = "Subject to image provider terms; verify intended use"
            if scene.media_type == "image":
                with Image.open(target) as image:
                    image.verify()
            else:
                duration(target, cfg.editing, "video")
            assets.append(
                {
                    "scene_id": scene.id,
                    "media": artifact(context.root, target, scene.media_type).model_dump(),
                    "provenance": provenance,
                    "license": license_name,
                }
            )
        return {**previous.model_dump(mode="json"), "assets": {"items": assets}}
