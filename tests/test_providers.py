import base64
import json
from io import BytesIO

import httpx
import pytest
from PIL import Image

from pipeline.config import MediaItem
from pipeline.models import Source
from pipeline.orchestrator import Orchestrator
from pipeline.providers.api import ProviderError, TextProvider
from pipeline.providers.media import demo_audio, demo_image, execute
from pipeline.providers.research import collect
from pipeline.registry import SKILLS
from pipeline.skill import Context
from skills.pesquisa_titulos import ResearchDraft


def test_live_text_adapter_uses_channel_and_validates_json(config, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "private-test-key")
    config.channel.language = "de-DE"
    config.channel.tone = "Investigative"
    config.prompts["pesquisa_titulos"] = "custom prompt"

    def fake_post(url, **kwargs):
        assert url.endswith("/chat/completions")
        assert kwargs["headers"]["Authorization"] == "Bearer private-test-key"
        body = kwargs["json"]
        assert "de-DE" in body["messages"][0]["content"]
        assert "Investigative" in body["messages"][0]["content"]
        assert "custom prompt" in body["messages"][1]["content"]
        assert "revision" in body["messages"][1]["content"]
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "summary": "Research summary",
                                    "candidates": [
                                        {
                                            "id": "t1",
                                            "title": "Title",
                                            "angle": "Angle",
                                            "rationale": "Reason",
                                            "source_ids": ["source"],
                                        }
                                    ],
                                }
                            )
                        },
                        "finish_reason": "stop",
                    }
                ]
            },
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    result = TextProvider(config).generate(
        "pesquisa_titulos", "Task", ResearchDraft, {}, "revision"
    )
    assert result.candidates[0].title == "Title"


def test_provider_errors_redact_keys_and_no_retry(config, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "secret-do-not-log")
    calls = []

    def failure(*args, **kwargs):
        calls.append(1)
        return httpx.Response(429, text="secret-do-not-log")

    monkeypatch.setattr(httpx, "post", failure)
    with pytest.raises(ProviderError, match="HTTP 429") as exc:
        TextProvider(config).generate("pesquisa_titulos", "Task", ResearchDraft, {})
    assert "secret-do-not-log" not in str(exc.value)
    assert len(calls) == 1


def test_youtube_research_collects_real_ids(config, monkeypatch):
    config.research.provider = "youtube"
    monkeypatch.setenv("YOUTUBE_API_KEY", "unit-test-key")
    original = httpx.Client

    def handler(request):
        assert request.url.params["q"]
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "id": {"videoId": "abc123"},
                        "snippet": {"title": "A real search result", "description": "A snippet"},
                    }
                ]
            },
        )

    monkeypatch.setattr(
        httpx, "Client", lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs)
    )
    sources = collect(config, "Test topic")
    assert sources[0].url == "https://www.youtube.com/watch?v=abc123"
    assert "not fact verification" in sources[0].excerpt


def test_production_pipeline_with_mocked_http_not_demo(config, monkeypatch, tmp_path):
    from pipeline.approvals import PendingApproval

    monkeypatch.setenv("OPENAI_API_KEY", "unit-test-key")
    config.research.sources = [
        Source(
            id="s1",
            title="Supplied evidence",
            url="https://example.org/evidence",
            excerpt="Editorial evidence supplied by the channel owner.",
        )
    ]
    config.research.title_count = 1
    config.thumbnail.variants = 1
    config.speech.instructions = "Speak clearly"
    buffer = BytesIO()
    Image.new("RGB", (1280, 720), "green").save(buffer, "PNG")
    image_b64 = base64.b64encode(buffer.getvalue()).decode()
    audio_file = tmp_path / "voice.wav"
    demo_audio(audio_file, seconds=1.5)  # A local test fixture, returned by the mocked API.
    called = []

    def post(url, **kwargs):
        body = kwargs["json"]
        called.append(url.rsplit("/", 1)[-1])
        if url.endswith("/images/generations"):
            return httpx.Response(200, json={"data": [{"b64_json": image_b64}]})
        if url.endswith("/audio/speech"):
            assert "Speak clearly" in body["instructions"]
            return httpx.Response(200, content=audio_file.read_bytes())
        user = json.loads(body["messages"][1]["content"])
        schema = user["schema"]["title"]
        replies = {
            "ResearchDraft": {
                "summary": "Niche research",
                "candidates": [
                    {
                        "id": "title1",
                        "title": "Approved title",
                        "angle": "An original angle",
                        "rationale": "Fits the audience",
                        "source_ids": ["s1"],
                    }
                ],
            },
            "Concepts": {
                "concepts": [{"id": "image1", "prompt": "Editorial science illustration"}]
            },
            "Script": {
                "title": "Approved title",
                "sections": [
                    {
                        "id": "intro",
                        "heading": "Opening",
                        "narration": "A complete spoken opening.",
                        "source_ids": ["s1"],
                    }
                ],
            },
            "VisualPlan": {
                "scenes": [
                    {
                        "id": "scene1",
                        "section_id": "intro",
                        "description": "First visual",
                        "prompt": "A diagram",
                        "search_terms": ["diagram"],
                        "weight": 1,
                        "media_type": "image",
                    },
                    {
                        "id": "scene2",
                        "section_id": "intro",
                        "description": "Second visual",
                        "prompt": "Another diagram",
                        "search_terms": ["diagram"],
                        "weight": 2,
                        "media_type": "image",
                    },
                ]
            },
        }
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"finish_reason": "stop", "message": {"content": json.dumps(replies[schema])}}
                ]
            },
        )

    monkeypatch.setattr(httpx, "post", post)
    run = Orchestrator.create(config)
    with pytest.raises(PendingApproval):
        run.run()
    run.decide("pesquisa_titulos", "reviewer", True, "title1")
    with pytest.raises(PendingApproval):
        run.run()
    run.decide("thumbnail", "reviewer", True, "image1")
    result = run.run()
    assert result.video.demo is False
    assert result.video.file.path == "final.mp4"
    assert called.count("speech") == 1
    assert called.count("generations") == 3
    assert result.video.duration_seconds <= 1.8


def test_local_narration_and_tagged_image_library(config, tmp_path):
    from tests.test_contracts import approved_thumbnail_output

    run, payload = approved_thumbnail_output(config)
    context = Context(config, run.root, demo=True)
    previous = SKILLS["roteiro"].input_model.model_validate(payload)
    script = SKILLS["roteiro"](previous, context)
    visual = SKILLS["plano_visual"](script, context)
    voice = tmp_path / "voice.wav"
    demo_audio(voice)
    config.narration.provider = "files"
    config.narration.files = {s.id: voice for s in script.script.sections}
    narration = SKILLS["narracao"](visual, Context(config, run.root))
    image = tmp_path / "source.jpg"
    demo_image(image, "source", (320, 180))
    config.media.provider = "library"
    config.media.library = [
        MediaItem(path=image, tags=[visual.topic], license="owned", source="local test")
    ]
    result = SKILLS["imagens"](narration, Context(config, run.root))
    assert all(a.provenance == "local test" for a in result.assets.items)
    config.media.library[0].tags = ["unrelated-tag"]
    with pytest.raises(ValueError, match="No tagged library match"):
        SKILLS["imagens"](narration, Context(config, run.root))
    # Mix real B-roll and still images, including a shorter looped source clip.
    config.media.library[0].tags = [visual.topic]
    clip = tmp_path / "clip.mp4"
    execute(
        [
            config.editing.ffmpeg,
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=red:s=320x180:r=12:d=0.5",
            "-c:v",
            "libx264",
            str(clip),
        ],
        30,
    )
    config.media.library.append(
        MediaItem(path=clip, tags=[visual.topic], license="owned", source="local B-roll")
    )
    narration.visual_plan.scenes[0].media_type = "video"
    mixed = SKILLS["imagens"](narration, Context(config, run.root))
    assert mixed.assets.items[0].media.kind == "video"
    edited = SKILLS["edicao"](mixed, Context(config, run.root))
    assert abs(edited.video.duration_seconds - 3) < 0.1
