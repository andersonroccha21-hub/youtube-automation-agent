from pydantic import Field

from pipeline.models import Brief, Model, Research, ResearchOutput, Source, Text, Title
from pipeline.providers.research import collect
from pipeline.skill import Context, Skill


class ResearchDraft(Model):
    summary: Text
    candidates: list[Title] = Field(min_length=1)


class PesquisaTitulos(Skill):
    name = "pesquisa_titulos"
    input_model = Brief
    output_model = ResearchOutput

    def execute(self, previous: Brief, context: Context) -> dict:
        count = context.config.research.title_count
        if context.demo:
            sources = [
                Source(
                    id="demo",
                    title="Demonstration fixture",
                    url="demo://fixture",
                    excerpt="Synthetic input for pipeline testing; not real research.",
                )
            ]
            result = ResearchDraft(
                summary="DEMO: no live niche research was performed.",
                candidates=[
                    Title(
                        id=f"t{i}",
                        title=f"DEMO {i}: {previous.topic}"[:100],
                        angle=f"Demonstration angle {i}",
                        rationale="Pipeline validation fixture",
                        source_ids=["demo"],
                    )
                    for i in range(1, count + 1)
                ],
            )
        else:
            sources = collect(context.config, previous.topic)
            result = context.text.generate(
                self.name,
                f"Research the niche from the supplied evidence and propose exactly {count} original "
                "titles with distinct angles. Explain the fit to the channel audience. "
                "Use only supplied source IDs. Do not treat search snippets as verified facts.",
                ResearchDraft,
                {
                    "brief": previous.model_dump(mode="json"),
                    "sources": [s.model_dump(mode="json") for s in sources],
                },
                context.feedback,
            )
        if len(result.candidates) != count:
            raise ValueError("Research provider returned the wrong number of titles")
        research = Research(sources=sources, **result.model_dump(mode="json"))
        return {**previous.model_dump(mode="json"), "research": research.model_dump(mode="json")}
