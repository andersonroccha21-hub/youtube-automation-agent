from pydantic import Field

from pipeline.models import Identifier, Model, ResearchOutput, Text, ThumbnailOutput
from pipeline.providers.media import demo_image
from pipeline.skill import Context, Skill
from pipeline.storage import artifact


class Concept(Model):
    id: Identifier
    prompt: Text


class Concepts(Model):
    concepts: list[Concept] = Field(min_length=1)


class Thumbnail(Skill):
    name = "thumbnail"
    input_model = ResearchOutput
    output_model = ThumbnailOutput

    def execute(self, previous: ResearchOutput, context: Context) -> dict:
        title = previous.research.selected()
        cfg = context.config
        if context.demo:
            concepts = Concepts(
                concepts=[
                    Concept(id=f"thumb{i}", prompt=f"DEMO variant {i}: {title.title}")
                    for i in range(1, cfg.thumbnail.variants + 1)
                ]
            )
        else:
            concepts = context.text.generate(
                self.name,
                f"Create exactly {cfg.thumbnail.variants} distinct thumbnail image prompts in English, "
                "communicating the approved title without changing its promise. "
                "If text appears in the image, it must use the channel language. "
                + cfg.thumbnail.prompt,
                Concepts,
                previous.model_dump(mode="json"),
                context.feedback,
            )
        if len(concepts.concepts) != cfg.thumbnail.variants:
            raise ValueError("Thumbnail provider returned the wrong number of variants")
        candidates = []
        for concept in concepts.concepts:
            target = context.path(f"assets/thumbnail/{concept.id}.jpg")
            prompt = (
                f"{concept.prompt}\nAesthetic: {cfg.channel.aesthetic}\n"
                f"Rules: {'; '.join(cfg.channel.rules)}\n{cfg.thumbnail.prompt}\n"
                f"{cfg.prompts.get(self.name, '')}\nRevision: {context.feedback}"
            )
            if context.demo:
                demo_image(target, concept.prompt, (1280, 720))
            else:
                context.image.generate(prompt, target, (1280, 720))
            candidates.append(
                {
                    "id": concept.id,
                    "prompt": prompt,
                    "image": artifact(context.root, target, "image").model_dump(),
                }
            )
        return {**previous.model_dump(mode="json"), "thumbnail": {"candidates": candidates}}
