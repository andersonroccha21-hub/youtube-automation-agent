"""Media inspection and FFmpeg rendering use argument lists, never a shell."""

from __future__ import annotations

import json
import math
import struct
import subprocess
import wave
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw

from pipeline.config import EditingConfig
from pipeline.storage import atomic_bytes


def execute(args: list[str], timeout: int):
    try:
        return subprocess.run(args, check=True, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError as exc:
        raise ValueError(f"Executable not found: {args[0]}") from exc
    except subprocess.CalledProcessError as exc:
        raise ValueError(f"{Path(args[0]).name} failed: {exc.stderr[-2000:]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise ValueError(f"{Path(args[0]).name} exceeded {timeout}s timeout") from exc


def probe(path: Path, config: EditingConfig) -> dict:
    result = execute(
        [
            config.ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration:stream=codec_type,width,height,duration",
            "-of",
            "json",
            str(path),
        ],
        30,
    )
    return json.loads(result.stdout)


def duration(path: Path, config: EditingConfig, kind="audio") -> float:
    info = probe(path, config)
    if not any(s["codec_type"] == kind for s in info.get("streams", [])):
        raise ValueError(f"Media has no {kind} stream: {path}")
    seconds = float(info["format"]["duration"])
    if not math.isfinite(seconds) or seconds <= 0:
        raise ValueError(f"Invalid media duration: {path}")
    return seconds


def demo_image(target: Path, label: str, size: tuple[int, int]):
    image = Image.new("RGB", size, "#192c44")
    draw = ImageDraw.Draw(image)
    draw.rectangle((20, 20, size[0] - 20, size[1] - 20), outline="#55d6c2", width=4)
    draw.text((36, 42), "DEMO - NOT PRODUCTION MEDIA", fill="white")
    draw.text((36, 80), label[:100].encode("ascii", "replace").decode(), fill="#55d6c2")
    buffer = BytesIO()
    image.save(buffer, "JPEG")
    atomic_bytes(target, buffer.getvalue())


def demo_audio(target: Path, seconds=1.0):
    buffer = BytesIO()
    rate = 24000
    with wave.open(buffer, "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(rate)
        stream.writeframes(
            b"".join(
                struct.pack("<h", int(1200 * math.sin(2 * math.pi * 440 * i / rate)))
                for i in range(int(rate * seconds))
            )
        )
    atomic_bytes(target, buffer.getvalue())


def render_scene(media: Path, target: Path, frames: int, media_type: str, config: EditingConfig):
    target.parent.mkdir(parents=True, exist_ok=True)
    visual = ["-loop", "1"] if media_type == "image" else ["-stream_loop", "-1"]
    filters = (
        f"scale={config.width}:{config.height}:force_original_aspect_ratio=increase,"
        f"crop={config.width}:{config.height},setsar=1,fps={config.fps},format=yuv420p"
    )
    # Render silent visual clips; encode the full narration only once at final muxing.
    execute(
        [
            config.ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            *visual,
            "-i",
            str(media),
            "-map",
            "0:v:0",
            "-vf",
            filters,
            "-frames:v",
            str(frames),
            "-c:v",
            "libx264",
            "-preset",
            config.preset,
            "-crf",
            str(config.crf),
            "-an",
            "-movflags",
            "+faststart",
            str(target),
        ],
        config.timeout_seconds,
    )


def normalize_audio(source: Path, target: Path, config: EditingConfig):
    execute(
        [
            config.ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source),
            "-vn",
            "-c:a",
            "pcm_s16le",
            "-ar",
            "48000",
            "-ac",
            "2",
            str(target),
        ],
        config.timeout_seconds,
    )


def concatenate(
    clips: list[Path],
    narration: list[Path],
    root: Path,
    target: Path,
    config: EditingConfig,
    seconds: float,
):
    # Generated clip names are identifiers, free of user-provided quotes or newlines.
    listing = root / "clips.ffconcat"
    atomic_bytes(
        listing,
        ("ffconcat version 1.0\n" + "".join(f"file '{clip.name}'\n" for clip in clips)).encode(),
    )
    normalized = []
    for index, source in enumerate(narration):
        audio = root / f"audio_{index:04d}.wav"
        normalize_audio(source, audio, config)
        normalized.append(audio)
    audio_list = root / "audio.ffconcat"
    atomic_bytes(
        audio_list,
        (
            "ffconcat version 1.0\n" + "".join(f"file '{audio.name}'\n" for audio in normalized)
        ).encode(),
    )
    temporary = target.with_name("final.writing.mp4")
    execute(
        [
            config.ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "concat",
            "-safe",
            "1",
            "-i",
            str(listing),
            "-f",
            "concat",
            "-safe",
            "1",
            "-i",
            str(audio_list),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-t",
            str(seconds),
            "-movflags",
            "+faststart",
            str(temporary),
        ],
        config.timeout_seconds,
    )
    info = probe(temporary, config)
    if not any(s["codec_type"] == "audio" for s in info["streams"]):
        raise ValueError("Final video has no audio stream")
    if not any(s["codec_type"] == "video" for s in info["streams"]):
        raise ValueError("Final video has no video stream")
    temporary.replace(target)
    return info
