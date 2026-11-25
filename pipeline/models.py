"""JSON contracts shared by independently executable skills."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Text = Annotated[str, Field(min_length=1)]
Identifier = Annotated[str, Field(pattern=r"^[a-zA-Z0-9_-]+$")]
Positive = Annotated[float, Field(gt=0, allow_inf_nan=False)]
STAGES = (
    "pesquisa_titulos",
    "thumbnail",
    "roteiro",
    "plano_visual",
    "narracao",
    "imagens",
    "edicao",
)
Stage = Literal[
    "pesquisa_titulos", "thumbnail", "roteiro", "plano_visual", "narracao", "imagens", "edicao"
]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class Source(Model):
    id: Identifier
    title: Text
    url: Text
    excerpt: Text


class Brief(Model):
    topic: Text


class Title(Model):
    id: Identifier
    title: Annotated[str, Field(min_length=1, max_length=100)]
    angle: Text
    rationale: Text
    source_ids: list[Identifier] = Field(min_length=1)


class Research(Model):
    summary: Text
    sources: list[Source] = Field(min_length=1)
    candidates: list[Title] = Field(min_length=1)
    selected_id: Identifier | None = None

    @model_validator(mode="after")
    def references(self):
        unique(self.sources)
        unique(self.candidates)
        known = {s.id for s in self.sources}
        if any(set(t.source_ids) - known for t in self.candidates):
            raise ValueError("Title references unknown research sources")
        if self.selected_id and self.selected_id not in {t.id for t in self.candidates}:
            raise ValueError("Selected title does not exist")
        return self

    def selected(self) -> Title:
        if self.selected_id is None:
            raise ValueError("Title requires human selection")
        return next(t for t in self.candidates if t.id == self.selected_id)


class Artifact(Model):
    path: Text  # Relative to the run directory, never to the process CWD.
    sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    kind: Literal["image", "video", "audio", "json", "text"]


class ThumbnailCandidate(Model):
    id: Identifier
    prompt: Text
    image: Artifact


class Thumbnails(Model):
    candidates: list[ThumbnailCandidate] = Field(min_length=1)
    selected_id: Identifier | None = None

    @model_validator(mode="after")
    def selection(self):
        unique(self.candidates)
        if self.selected_id and self.selected_id not in {c.id for c in self.candidates}:
            raise ValueError("Selected thumbnail does not exist")
        return self

    def selected(self) -> ThumbnailCandidate:
        if self.selected_id is None:
            raise ValueError("Thumbnail requires human selection")
        return next(c for c in self.candidates if c.id == self.selected_id)


class Section(Model):
    id: Identifier
    heading: Text
    narration: Annotated[str, Field(min_length=1, max_length=3500)]
    source_ids: list[Identifier] = Field(default_factory=list)


class Script(Model):
    title: Text
    sections: list[Section] = Field(min_length=1)

    @model_validator(mode="after")
    def sections_unique(self):
        unique(self.sections)
        return self


class Scene(Model):
    id: Identifier
    section_id: Identifier
    description: Text
    prompt: Text
    search_terms: list[Text] = Field(min_length=1)
    weight: Positive = 1.0
    media_type: Literal["image", "video"] = "image"


class VisualPlan(Model):
    scenes: list[Scene] = Field(min_length=1)

    @model_validator(mode="after")
    def scenes_unique(self):
        unique(self.scenes)
        return self


class AudioSegment(Model):
    section_id: Identifier
    audio: Artifact
    duration_seconds: Positive


class Narration(Model):
    segments: list[AudioSegment] = Field(min_length=1)


class VisualAsset(Model):
    scene_id: Identifier
    media: Artifact
    provenance: Text
    license: Text


class Assets(Model):
    items: list[VisualAsset] = Field(min_length=1)


class Video(Model):
    file: Artifact
    duration_seconds: Positive
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    demo: bool


class ResearchOutput(Brief):
    research: Research


class ThumbnailOutput(ResearchOutput):
    thumbnail: Thumbnails


class ScriptOutput(ThumbnailOutput):
    script: Script

    @model_validator(mode="after")
    def script_consistent(self):
        if self.script.title != self.research.selected().title:
            raise ValueError("Script changed the approved title")
        known = {s.id for s in self.research.sources}
        if any(set(s.source_ids) - known for s in self.script.sections):
            raise ValueError("Script references unknown sources")
        self.thumbnail.selected()
        return self


class VisualOutput(ScriptOutput):
    visual_plan: VisualPlan

    @model_validator(mode="after")
    def sections_covered(self):
        if {s.section_id for s in self.visual_plan.scenes} != {s.id for s in self.script.sections}:
            raise ValueError("Visual plan must cover every script section and no others")
        return self


class NarrationOutput(VisualOutput):
    narration: Narration

    @model_validator(mode="after")
    def audio_coverage(self):
        ids = [s.section_id for s in self.narration.segments]
        if ids != [s.id for s in self.script.sections]:
            raise ValueError("Narration must follow script sections exactly, in order")
        return self


class ImagesOutput(NarrationOutput):
    assets: Assets

    @model_validator(mode="after")
    def scene_coverage(self):
        ids = [s.scene_id for s in self.assets.items]
        if len(ids) != len(set(ids)) or set(ids) != {s.id for s in self.visual_plan.scenes}:
            raise ValueError("Assets must cover each scene exactly once")
        expected = {s.id: s.media_type for s in self.visual_plan.scenes}
        if any(a.media.kind != expected[a.scene_id] for a in self.assets.items):
            raise ValueError("Asset type differs from visual plan")
        return self


class EditOutput(ImagesOutput):
    video: Video


def unique(items):
    ids = [item.id for item in items]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate identifiers")
