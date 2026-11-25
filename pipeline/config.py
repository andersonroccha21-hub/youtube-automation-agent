"""Channel settings are explicit, validated and resolved relative to their YAML."""

from pathlib import Path
from typing import Literal

import yaml
from pydantic import Field, field_validator, model_validator

from pipeline.models import Identifier, Model, Source, Stage, Text


class Channel(Model):
    id: Identifier
    name: Text
    niche: Text
    audience: Text
    language: Text
    tone: Text
    aesthetic: Text
    rules: list[Text] = Field(default_factory=list)
    target_duration_seconds: int = Field(default=300, ge=5, le=14400)


class API(Model):
    base_url: Text = "https://api.openai.com/v1"
    api_key_env: Text = "OPENAI_API_KEY"
    model: Text
    timeout_seconds: float = Field(default=180, gt=0, le=3600)

    @field_validator("base_url")
    @classmethod
    def valid_url(cls, value):
        if not value.startswith(("https://", "http://localhost:", "http://127.0.0.1:")):
            raise ValueError("API URL requires HTTPS or a local HTTP endpoint")
        return value.rstrip("/")


class TextAPI(API):
    max_tokens: int = Field(default=12000, ge=256, le=100000)
    json_mode: bool = True


class ImageAPI(API):
    size: Text = "1536x1024"


class SpeechAPI(API):
    voice: Text = "alloy"
    speed: float = Field(default=1.0, ge=0.25, le=4.0)
    instructions: Text | None = None


class ResearchConfig(Model):
    provider: Literal["provided", "youtube"] = "provided"
    sources: list[Source] = Field(default_factory=list)
    youtube_api_key_env: Text = "YOUTUBE_API_KEY"
    region: Text = "US"
    queries: list[Text] = Field(default_factory=list)
    max_results: int = Field(default=10, ge=1, le=50)
    title_count: int = Field(default=3, ge=1, le=10)


class ThumbnailConfig(Model):
    variants: int = Field(default=2, ge=1, le=5)
    prompt: Text = "Strong focal point, readable at small sizes, uncluttered composition."


class MediaItem(Model):
    path: Path
    tags: list[Text] = Field(min_length=1)
    license: Text
    source: Text


class MediaConfig(Model):
    provider: Literal["generated", "library"] = "generated"
    library: list[MediaItem] = Field(default_factory=list)


class NarrationConfig(Model):
    provider: Literal["api", "files"] = "api"
    files: dict[Identifier, Path] = Field(default_factory=dict)


class EditingConfig(Model):
    width: int = Field(default=1920, ge=160, le=3840, multiple_of=2)
    height: int = Field(default=1080, ge=90, le=3840, multiple_of=2)
    fps: int = Field(default=30, ge=1, le=60)
    preset: Literal["ultrafast", "fast", "medium", "slow"] = "medium"
    crf: int = Field(default=20, ge=0, le=51)
    ffmpeg: Text = "ffmpeg"
    ffprobe: Text = "ffprobe"
    timeout_seconds: int = Field(default=3600, ge=10, le=86400)


class ApprovalConfig(Model):
    mode: Literal["interactive", "file"] = "interactive"
    optional: dict[Stage, bool] = Field(default_factory=dict)

    def required(self, stage: Stage) -> bool:
        return stage in ("pesquisa_titulos", "thumbnail") or self.optional.get(stage, False)


class Config(Model):
    schema_version: Literal[1] = 1
    channel: Channel
    text: TextAPI
    image: ImageAPI
    speech: SpeechAPI
    research: ResearchConfig = Field(default_factory=ResearchConfig)
    thumbnail: ThumbnailConfig = Field(default_factory=ThumbnailConfig)
    narration: NarrationConfig = Field(default_factory=NarrationConfig)
    media: MediaConfig = Field(default_factory=MediaConfig)
    editing: EditingConfig = Field(default_factory=EditingConfig)
    approvals: ApprovalConfig = Field(default_factory=ApprovalConfig)
    prompts: dict[Stage, Text] = Field(default_factory=dict)
    output_root: Path = Path("../../runs")

    @model_validator(mode="after")
    def ids_unique(self):
        ids = [s.id for s in self.research.sources]
        if len(ids) != len(set(ids)):
            raise ValueError("Research source IDs must be unique")
        return self


def load_config(path: Path) -> Config:
    path = path.resolve()
    try:
        with path.open(encoding="utf-8") as stream:
            raw = yaml.safe_load(stream)
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML syntax: {path.name}") from exc
    config = Config.model_validate(raw)
    config.output_root = (path.parent / config.output_root).resolve()
    for item in config.media.library:
        item.path = (path.parent / item.path).resolve()
    config.narration.files = {
        key: (path.parent / value).resolve() for key, value in config.narration.files.items()
    }
    return config
