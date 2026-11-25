"""Evidence comes from a supplied catalog or real YouTube search, never invented URLs."""

import httpx

from pipeline.config import Config
from pipeline.models import Source
from pipeline.providers.api import ProviderError, secret


def collect(config: Config, topic: str) -> list[Source]:
    settings = config.research
    if settings.provider == "provided":
        if not settings.sources:
            raise ValueError("research.sources is required with provider=provided")
        return settings.sources
    sources = {s.id: s for s in settings.sources}
    with httpx.Client(timeout=30) as client:
        for query in settings.queries or [f"{config.channel.niche} {topic}"]:
            try:
                response = client.get(
                    "https://www.googleapis.com/youtube/v3/search",
                    params={
                        "key": secret(settings.youtube_api_key_env),
                        "part": "snippet",
                        "type": "video",
                        "q": query,
                        "maxResults": settings.max_results,
                        "regionCode": settings.region,
                        "relevanceLanguage": config.channel.language.split("-")[0],
                    },
                )
            except httpx.HTTPError as exc:
                raise ProviderError("YouTube research transport error; check connectivity") from exc
            if response.is_error:
                raise ValueError(f"YouTube research returned HTTP {response.status_code}")
            for item in response.json().get("items", []):
                video_id = item["id"]["videoId"]
                snippet = item["snippet"]
                source = Source(
                    id=f"yt_{video_id}",
                    title=snippet["title"],
                    url=f"https://www.youtube.com/watch?v={video_id}",
                    excerpt=(snippet.get("description") or snippet["title"])
                    + " [YouTube search metadata: evidence of topic coverage, not fact verification.]",
                )
                sources[source.id] = source
    if not sources:
        raise ValueError("No research evidence found; provide sources or change queries")
    return list(sources.values())
