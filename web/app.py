"""Dashboard API. Paths are selected from known channel configs, never supplied by clients."""

from __future__ import annotations

import os
import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated
from urllib.parse import quote, urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from pipeline.config import Config, load_config
from pipeline.models import STAGES, Stage
from pipeline.orchestrator import Orchestrator, RunState
from pipeline.preflight import check
from pipeline.registry import SKILLS
from pipeline.storage import digest, file_digest, inside, read_json
from web.runner import Runner

ROOT = Path(__file__).resolve().parents[1]
STATIC = Path(__file__).parent / "static"
LABELS = {
    "pesquisa_titulos": "Pesquisa e títulos",
    "thumbnail": "Thumbnail",
    "roteiro": "Roteiro",
    "plano_visual": "Plano visual",
    "narracao": "Narração",
    "imagens": "Imagens",
    "edicao": "Edição",
}
SAFE_ID = re.compile(r"^[a-zA-Z0-9_.+:-]+$")
NonBlank = Annotated[str, Field(min_length=1, max_length=200)]
Hash = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class Body(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class NewRun(Body):
    channel_id: NonBlank
    topic: Annotated[str, Field(min_length=1, max_length=2000)]
    demo: bool = False


class Approval(Body):
    stage: Stage
    reviewer: NonBlank
    artifact_digest: Hash
    selected_id: NonBlank | None = None
    approve: bool = True
    feedback: str = Field(default="", max_length=4000)


class Revision(Body):
    stage: Stage
    feedback: Annotated[str, Field(min_length=1, max_length=4000)]


class Channels:
    def __init__(self, root: Path):
        self.root = root.resolve()

    def scan(self):
        found: dict[str, tuple[Path, Config]] = {}
        errors, duplicates = [], set()
        paths = sorted(set(self.root.rglob("*.yaml")) | set(self.root.rglob("*.yml")))
        for path in paths:
            if not path.resolve().is_relative_to(self.root):
                errors.append(
                    {"path": str(path.relative_to(self.root)), "error": "YAML fora de channels/."}
                )
                continue
            try:
                config = load_config(path)
                key = config.channel.id
                if key in found or key in duplicates:
                    duplicates.add(key)
                    found.pop(key, None)
                    errors.append(
                        {
                            "path": str(path.relative_to(self.root)),
                            "error": f"channel.id duplicado: {key}",
                        }
                    )
                else:
                    found[key] = (path, config)
            except (OSError, ValueError, TypeError):
                errors.append(
                    {
                        "path": str(path.relative_to(self.root)),
                        "error": "Configuração YAML inválida. Valide pelo CLI.",
                    }
                )
        return found, errors

    def config(self, channel_id: str) -> Config:
        found, _ = self.scan()
        if channel_id not in found:
            raise HTTPException(404, "Canal não encontrado ou configuração inválida.")
        return found[channel_id][1]

    def run(self, channel_id: str, run_id: str) -> Orchestrator:
        if not SAFE_ID.fullmatch(run_id):
            raise HTTPException(404, "Execução não encontrada.")
        config = self.config(channel_id)
        parent = (config.output_root / channel_id).resolve()
        root = (parent / run_id).resolve()
        if root.parent != parent or not (root / "state.json").is_file():
            raise HTTPException(404, "Execução não encontrada.")
        state = RunState.model_validate(read_json(root / "state.json"))
        if state.config.channel.id != channel_id:
            raise HTTPException(409, "O estado pertence a outro canal.")
        # Resume the original immutable snapshot, including its approval policy.
        run = Orchestrator(state.config, root)
        run.state()
        return run


def artifacts(data):
    if isinstance(data, dict):
        if {"path", "sha256", "kind"} <= data.keys():
            yield data
        for value in data.values():
            yield from artifacts(value)
    elif isinstance(data, list):
        for value in data:
            yield from artifacts(value)


def checkpoint(run: Orchestrator, state: RunState, stage: str):
    if stage not in state.checkpoints:
        raise HTTPException(404, "Esta etapa ainda não produziu um resultado.")
    output = SKILLS[stage].output_model.model_validate(read_json(run.checkpoint_path(stage)))
    if digest(output) != state.checkpoints[stage]:
        raise HTTPException(409, "O checkpoint foi alterado. Revise a etapa antes de continuar.")
    return output


def media_url(run: Orchestrator, path: str):
    return f"/api/channels/{quote(run.config.channel.id)}/runs/{quote(run.root.name)}/media/{quote(path, safe='/')}"


def snapshot(run: Orchestrator, runner: Runner, *, details=True):
    state = run.state()
    busy = runner.busy(run)
    interrupted = state.status == "running" and not busy
    stages, completed = [], 0
    for name in STAGES:
        decision = state.approvals.get(name)
        approved = (
            decision
            and decision.status == "approved"
            and decision.artifact_digest == state.checkpoints.get(name)
        )
        done = name in state.checkpoints and (not state.config.approvals.required(name) or approved)
        status = "completed" if done else "pending"
        if state.current == name:
            if state.status == "pending_approval":
                status = "pending_approval"
            elif state.status in ("failed", "rejected") or interrupted:
                status = "failed" if state.status != "rejected" else "rejected"
            elif busy and not done:
                status = "running"
        if status == "completed":
            completed += 1
        stages.append(
            {
                "id": name,
                "label": LABELS[name],
                "status": status,
                "has_output": name in state.checkpoints,
                "approval_required": state.config.approvals.required(name),
            }
        )
    result = {
        "id": run.root.name,
        "channel_id": state.config.channel.id,
        "channel_name": state.config.channel.name,
        "topic": state.brief.topic,
        "demo": state.demo,
        "status": "interrupted" if interrupted else state.status,
        "busy": busy,
        "current": state.current,
        "created_at": state.created_at,
        "updated_at": state.updated_at,
        "completed_stages": completed,
        "total_stages": len(STAGES),
        "progress": round(completed / len(STAGES) * 100),
        "stages": stages,
        "error": runner.error(run) or state.last_error,
    }
    if not details:
        return result
    result.update(review=None, video=None)
    if state.status == "pending_approval" and state.current in state.checkpoints:
        output = run._load(state, state.current)  # Verify exactly the media the human will review.
        review = {
            "stage": state.current,
            "artifact_digest": digest(output),
            "label": LABELS[state.current],
            "candidates": [],
            "content": None,
        }
        if state.current == "pesquisa_titulos":
            review["summary"] = output.research.summary
            review["sources"] = [s.model_dump(mode="json") for s in output.research.sources]
            review["candidates"] = [c.model_dump(mode="json") for c in output.research.candidates]
        elif state.current == "thumbnail":
            review["candidates"] = [
                {"id": c.id, "prompt": c.prompt, "image_url": media_url(run, c.image.path)}
                for c in output.thumbnail.candidates
            ]
        else:
            field = {
                "roteiro": "script",
                "plano_visual": "visual_plan",
                "narracao": "narration",
                "imagens": "assets",
                "edicao": "video",
            }[state.current]
            review["content"] = output.model_dump(mode="json")[field]
            review["media"] = [
                {**item, "url": media_url(run, item["path"])}
                for item in artifacts(review["content"])
            ]
        result["review"] = review
    if state.status == "completed" and "edicao" in state.checkpoints:
        output = checkpoint(run, state, "edicao")
        result["video"] = {
            **output.video.model_dump(mode="json"),
            "url": media_url(run, output.video.file.path),
        }
        result["selected_title"] = output.research.selected().title
    return result


def create_app(channels_dir: Path | None = None) -> FastAPI:
    channels = Channels(
        channels_dir or Path(os.environ.get("YOUTUBE_CHANNELS_DIR", ROOT / "channels"))
    )
    runner = Runner()

    @asynccontextmanager
    async def lifespan(app):
        yield
        runner.shutdown()

    app = FastAPI(title="Darklab Studio · YouTube Pipeline", version="3.1.0", lifespan=lifespan)
    app.state.runner = runner
    app.add_middleware(
        TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "[::1]", "testserver"]
    )

    @app.middleware("http")
    async def local_origin(request: Request, call_next):
        origin = request.headers.get("origin")
        if request.method not in ("GET", "HEAD", "OPTIONS") and origin:
            parsed = urlsplit(origin)
            if parsed.netloc != request.url.netloc or parsed.scheme != request.url.scheme:
                return JSONResponse(
                    {"detail": "Origem da solicitação não permitida."}, status_code=403
                )
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(ValueError)
    async def conflict(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=409)

    @app.exception_handler(OSError)
    async def storage_error(request, exc):
        return JSONResponse(
            {"detail": "Não foi possível acessar os arquivos da execução."}, status_code=409
        )

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(STATIC / "index.html")

    @app.get("/api/channels")
    def list_channels():
        found, errors = channels.scan()
        items = []
        for key, (path, config) in found.items():
            production_error = None
            try:
                check(config)
            except (OSError, ValueError) as exc:
                production_error = str(exc)
            items.append(
                {
                    "id": key,
                    "name": config.channel.name,
                    "niche": config.channel.niche,
                    "language": config.channel.language,
                    "config_path": str(path.relative_to(channels.root)),
                    "target_duration_seconds": config.channel.target_duration_seconds,
                    "production_ready": production_error is None,
                    "production_error": production_error,
                }
            )
        return {"channels": items, "errors": errors}

    @app.get("/api/channels/{channel_id}/runs")
    def list_runs(channel_id: str):
        config = channels.config(channel_id)
        items, errors = [], []
        for path in sorted((config.output_root / channel_id).glob("*/state.json"), reverse=True):
            try:
                run = channels.run(channel_id, path.parent.name)
                items.append(snapshot(run, runner, details=False))
            except (ValueError, OSError, HTTPException):
                errors.append({"id": path.parent.name, "error": "Estado inválido ou inacessível."})
        return {
            "runs": sorted(items, key=lambda r: r["created_at"], reverse=True),
            "errors": errors,
        }

    @app.post("/api/runs", status_code=202)
    def start_run(body: NewRun):
        config = channels.config(body.channel_id)
        try:
            check(config, body.demo)
        except (OSError, ValueError) as exc:
            raise HTTPException(422, str(exc)) from exc
        with runner.guard:
            if len(runner.jobs) >= 8:
                raise HTTPException(409, "A fila local está cheia.")
            run = Orchestrator.create(config, body.topic, body.demo)
            runner.submit(run)
        return snapshot(run, runner, details=False)

    @app.get("/api/channels/{channel_id}/runs/{run_id}")
    def get_run(channel_id: str, run_id: str):
        return snapshot(channels.run(channel_id, run_id), runner)

    @app.post("/api/channels/{channel_id}/runs/{run_id}/approve", status_code=202)
    def approve(channel_id: str, run_id: str, body: Approval):
        run = channels.run(channel_id, run_id)
        with runner.guard:
            runner.assert_idle(run)
            run.decide(
                body.stage,
                body.reviewer,
                body.approve,
                body.selected_id,
                body.feedback,
                expected_digest=body.artifact_digest,
            )
            if body.approve:
                runner.submit(run)
        return snapshot(run, runner, details=False)

    @app.post("/api/channels/{channel_id}/runs/{run_id}/resume", status_code=202)
    def resume(channel_id: str, run_id: str):
        run = channels.run(channel_id, run_id)
        with runner.guard:
            runner.assert_idle(run)
            state = run.state()
            if state.status in ("pending_approval", "rejected", "completed"):
                raise HTTPException(
                    409, "Aprove a etapa pendente ou solicite uma revisão antes de continuar."
                )
            runner.submit(run)
        return snapshot(run, runner, details=False)

    @app.post("/api/channels/{channel_id}/runs/{run_id}/revise", status_code=202)
    def revise(channel_id: str, run_id: str, body: Revision):
        run = channels.run(channel_id, run_id)
        with runner.guard:
            runner.assert_idle(run)
            run.revise(body.stage, body.feedback)
            runner.submit(run)
        return snapshot(run, runner, details=False)

    @app.get("/api/channels/{channel_id}/runs/{run_id}/checkpoints/{stage}")
    def get_checkpoint(channel_id: str, run_id: str, stage: Stage):
        run = channels.run(channel_id, run_id)
        return checkpoint(run, run.state(), stage).model_dump(mode="json")

    @app.get("/api/channels/{channel_id}/runs/{run_id}/media/{path:path}")
    def get_media(channel_id: str, run_id: str, path: str):
        run = channels.run(channel_id, run_id)
        state = run.state()
        available = {}
        for stage in reversed(STAGES):
            if stage in state.checkpoints:
                output = checkpoint(run, state, stage)
                available = {a["path"]: a for a in artifacts(output.model_dump(mode="json"))}
                break
        if path not in available:
            raise HTTPException(404, "Mídia não encontrada nesta execução.")
        target = inside(run.root, path)
        if not target.is_file() or file_digest(target) != available[path]["sha256"]:
            raise HTTPException(409, "O arquivo foi alterado ou removido; revise sua etapa.")
        return FileResponse(
            target, headers={"Content-Disposition": f'inline; filename="{target.name}"'}
        )

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app


app = create_app()
