"""Atomic JSON files, integrity checks and per-run process locking."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path

from pipeline.models import Artifact, Model


def plain(value):
    return value.model_dump(mode="json") if isinstance(value, Model) else value


def digest(value) -> str:
    return hashlib.sha256(
        json.dumps(plain(value), sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def file_digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def atomic_bytes(path: Path, content: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".writing-")
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def write_json(path: Path, value):
    atomic_bytes(path, (json.dumps(plain(value), ensure_ascii=False, indent=2) + "\n").encode())


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def inside(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("Artifact path escapes run directory")
    return path


def artifact(root: Path, path: Path, kind: str) -> Artifact:
    path = path.resolve()
    relative = str(path.relative_to(root.resolve()))
    if not path.is_file() or path.stat().st_size == 0:
        raise ValueError(f"Empty or missing artifact: {relative}")
    return Artifact(path=relative, sha256=file_digest(path), kind=kind)


def verify_artifacts(root: Path, data):
    data = plain(data)
    if isinstance(data, dict):
        if {"path", "sha256", "kind"} <= data.keys():
            path = inside(root, data["path"])
            if not path.is_file() or file_digest(path) != data["sha256"]:
                raise ValueError(f"Missing or modified artifact: {data['path']}; revise its stage")
        for value in data.values():
            verify_artifacts(root, value)
    elif isinstance(data, list):
        for value in data:
            verify_artifacts(root, value)


@contextmanager
def run_lock(root: Path):
    # Kernel releases flock even if the worker crashes; supported on macOS and Linux.
    import fcntl

    root.mkdir(parents=True, exist_ok=True)
    with (root / ".lock").open("a+") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError("Another process is operating on this run") from exc
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)
