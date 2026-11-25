"""Read-only readiness checks; never call paid providers here."""

import shutil

from pipeline.config import Config
from pipeline.providers.api import secret


def check(config: Config, demo: bool = False):
    for executable in (config.editing.ffmpeg, config.editing.ffprobe):
        if not shutil.which(executable):
            raise ValueError(f"Executable not found: {executable}; install FFmpeg and ffprobe")
    if demo:
        return
    for api in (config.text, config.image):
        secret(api.api_key_env)
    if config.narration.provider == "api":
        secret(config.speech.api_key_env)
    # Imported narration is checked at its stage: section IDs/files may be prepared
    # while the human reviews the script, before allowing that stage to proceed.
    if config.research.provider == "youtube":
        secret(config.research.youtube_api_key_env)
    elif not config.research.sources:
        raise ValueError(
            "Add real research.sources or set research.provider=youtube before production"
        )
    if config.media.provider == "library":
        if not config.media.library:
            raise ValueError("media.library cannot be empty with provider=library")
        for item in config.media.library:
            if not item.path.is_file():
                raise ValueError(f"Library file does not exist: {item.path}")
