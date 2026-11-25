from pipeline.models import Script, ScriptOutput, Section, ThumbnailOutput
from pipeline.skill import Context, Skill


class Roteiro(Skill):
    name = "roteiro"
    input_model = ThumbnailOutput
    output_model = ScriptOutput

    def execute(self, previous: ThumbnailOutput, context: Context) -> dict:
        title = previous.research.selected().title
        previous.thumbnail.selected()
        if context.demo:
            script = Script(
                title=title,
                sections=[
                    Section(id="hook", heading="DEMO Hook", narration=f"DEMO: {previous.topic}"),
                    Section(
                        id="body", heading="DEMO Body", narration="Synthetic content for testing."
                    ),
                    Section(id="cta", heading="DEMO CTA", narration="End of demonstration."),
                ],
            )
        else:
            script = context.text.generate(
                self.name,
                "Write the complete spoken script in channel.language with hook, development, payoff "
                "and CTA as ordered sections. No placeholders, summaries or stage directions in "
                "narration. Use <=3500 characters per section (split longer sections). Aim for "
                f"{context.config.channel.target_duration_seconds} seconds at natural speaking pace. "
                "Use only supplied evidence for factual claims and list its source IDs per section. "
                "Respect the exact approved title and the thumbnail promise.",
                Script,
                previous.model_dump(mode="json"),
                context.feedback,
            )
        return {**previous.model_dump(mode="json"), "script": script.model_dump(mode="json")}
