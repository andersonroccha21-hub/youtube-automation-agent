from pipeline.models import Scene, ScriptOutput, VisualOutput, VisualPlan
from pipeline.skill import Context, Skill


class PlanoVisual(Skill):
    name = "plano_visual"
    input_model = ScriptOutput
    output_model = VisualOutput

    def execute(self, previous: ScriptOutput, context: Context) -> dict:
        if context.demo:
            plan = VisualPlan(
                scenes=[
                    Scene(
                        id=f"scene_{i}",
                        section_id=section.id,
                        description=f"DEMO: {section.heading}",
                        prompt=f"DEMO visual {i}",
                        search_terms=[previous.topic],
                    )
                    for i, section in enumerate(previous.script.sections, 1)
                ]
            )
        else:
            plan = context.text.generate(
                self.name,
                "Plan visual scenes covering every script section. Use exact section IDs. "
                "Write detailed visual prompts in English, preserving visual continuity and the "
                "channel aesthetic. Use positive weights for relative scene durations within each "
                "section; real TTS duration will determine timing later. Include B-roll search terms. "
                + (
                    "Use media_type=image for all scenes (image generation provider)."
                    if context.config.media.provider == "generated"
                    else "Use image or video according to the available media library.\n"
                    + str(
                        [
                            {"tags": m.tags, "type": m.path.suffix}
                            for m in context.config.media.library
                        ]
                    )
                ),
                VisualPlan,
                previous.model_dump(mode="json"),
                context.feedback,
            )
        return {**previous.model_dump(mode="json"), "visual_plan": plan.model_dump(mode="json")}
