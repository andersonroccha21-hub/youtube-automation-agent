"""Sequential orchestration with durable checkpoints and non-bypassable review gates."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import Field

from pipeline.approvals import (
    Decision,
    PendingApproval,
    RejectedApproval,
    apply_selection,
    now,
    review_text,
)
from pipeline.config import Config
from pipeline.models import STAGES, Brief, Model, Stage, Text
from pipeline.registry import SKILLS
from pipeline.skill import Context
from pipeline.storage import digest, read_json, run_lock, verify_artifacts, write_json


class RunState(Model):
    schema_version: Literal[1] = 1
    config_digest: Text
    config: Config
    brief: Brief
    demo: bool
    created_at: Text
    updated_at: Text
    status: Literal["ready", "running", "pending_approval", "rejected", "failed", "completed"] = (
        "ready"
    )
    current: Stage | None = None
    checkpoints: dict[Stage, str] = Field(default_factory=dict)
    approvals: dict[Stage, Decision] = Field(default_factory=dict)
    feedback: dict[Stage, str] = Field(default_factory=dict)
    last_error: str | None = None


class Orchestrator:
    def __init__(self, config: Config, root: Path):
        self.config = config
        self.root = root.resolve()
        self.state_path = self.root / "state.json"

    @classmethod
    def create(cls, config: Config, topic: str | None = None, demo: bool = False):
        run_id = now().replace(":", "").replace("+", "_") + "-" + uuid4().hex[:8]
        root = config.output_root / config.channel.id / run_id
        run = cls(config, root)
        with run_lock(root):
            timestamp = now()
            run._save(
                RunState(
                    config_digest=digest(config),
                    config=config,
                    brief=Brief(topic=topic or config.channel.niche),
                    demo=demo,
                    created_at=timestamp,
                    updated_at=timestamp,
                )
            )
        return run

    def _save(self, state: RunState):
        state.updated_at = now()
        write_json(self.state_path, state)

    def state(self) -> RunState:
        state = RunState.model_validate(read_json(self.state_path))
        if (
            state.config_digest != digest(self.config)
            or digest(state.config) != state.config_digest
        ):
            raise ValueError(
                "Channel config changed or belongs to another channel; use the original YAML or start a new run"
            )
        return state

    def checkpoint_path(self, stage: str) -> Path:
        if stage not in STAGES:
            raise ValueError("Unknown stage")
        return self.root / "checkpoints" / f"{stage}.json"

    def _load(self, state: RunState, stage: str) -> Model:
        output = SKILLS[stage].output_model.model_validate(read_json(self.checkpoint_path(stage)))
        if digest(output) != state.checkpoints[stage]:
            raise ValueError(f"Checkpoint {stage} changed; use --revise {stage} to regenerate")
        verify_artifacts(self.root, output)
        return output

    def _gate(
        self, state: RunState, stage: Stage, output: Model, interactive: bool | None = None
    ) -> Model:
        if not self.config.approvals.required(stage):
            return output
        decision = state.approvals.get(stage)
        if decision:
            if decision.artifact_digest != digest(output):
                raise ValueError("Approval belongs to a different artifact version")
            if decision.status == "rejected":
                raise RejectedApproval(f"{stage} rejected: {decision.feedback}; revise this stage")
            return apply_selection(stage, output, decision.selected_id)
        state.status = "pending_approval"
        self._save(state)
        print(review_text(stage, output, self.root))
        if interactive is False or self.config.approvals.mode == "file" or not sys.stdin.isatty():
            raise PendingApproval(f"Run paused for human approval: {stage}")
        try:
            command = input(
                "Type 'approve' or 'reject' (anything else leaves the run paused): "
            ).strip()
            if command not in ("approve", "reject"):
                raise PendingApproval(f"Awaiting explicit approval for {stage}")
            reviewer = input("Reviewer name: ").strip()
            selected_id = None
            feedback = ""
            if command == "approve":
                if stage in ("pesquisa_titulos", "thumbnail"):
                    selected_id = input("Candidate ID: ").strip()
                selected = apply_selection(stage, output, selected_id)
            else:
                feedback = input("Rejection feedback: ").strip()
                if not feedback:
                    raise PendingApproval("Rejection requires feedback")
            decision = Decision(
                stage=stage,
                status="approved" if command == "approve" else "rejected",
                artifact_digest=digest(output),
                reviewer=reviewer,
                selected_id=selected_id,
                feedback=feedback,
                decided_at=now(),
            )
        except (EOFError, KeyboardInterrupt) as exc:
            raise PendingApproval(f"Review interrupted for {stage}") from exc
        state.approvals[stage] = decision
        state.status = "ready" if command == "approve" else "rejected"
        self._save(state)
        if command == "reject":
            raise RejectedApproval(f"{stage} rejected; use --revise with feedback")
        return selected

    def run(self, *, interactive: bool | None = None) -> Model:
        with run_lock(self.root):
            state = self.state()
            previous = state.brief
            try:
                for stage in STAGES:
                    state.current = stage
                    if stage in state.checkpoints:
                        output = self._load(state, stage)
                        prior = previous.model_dump(mode="json")
                        if any(
                            output.model_dump(mode="json").get(k) != v for k, v in prior.items()
                        ):
                            raise ValueError(
                                f"Checkpoint {stage} has inconsistent upstream context"
                            )
                    else:
                        state.status = "running"
                        state.last_error = None
                        self._save(state)
                        print(
                            f"Running {stage} ({'DEMO' if state.demo else 'production'})",
                            flush=True,
                        )
                        context = Context(
                            self.config, self.root, state.demo, state.feedback.get(stage, "")
                        )
                        output = SKILLS[stage](previous, context)
                        # Skills cannot preselect candidates on behalf of a human.
                        if stage == "pesquisa_titulos" and output.research.selected_id is not None:
                            raise ValueError("Research attempted to preselect a title")
                        if stage == "thumbnail" and output.thumbnail.selected_id is not None:
                            raise ValueError("Thumbnail skill attempted to preselect a candidate")
                        write_json(self.checkpoint_path(stage), output)
                        state.checkpoints[stage] = digest(output)
                        self._save(state)
                    previous = self._gate(state, stage, output, interactive)
                state.status = "completed"
                state.current = None
                state.last_error = None
                self._save(state)
                write_json(self.root / "result.json", previous)
                return previous
            except PendingApproval:
                raise
            except RejectedApproval:
                state.status = "rejected"
                self._save(state)
                raise
            except (Exception, KeyboardInterrupt) as exc:
                state.status = "failed"
                state.last_error = f"{type(exc).__name__}: {exc}"
                self._save(state)
                raise

    def decide(
        self,
        stage: Stage,
        reviewer: str,
        approve: bool,
        selected_id: str | None = None,
        feedback: str = "",
        expected_digest: str | None = None,
    ):
        with run_lock(self.root):
            state = self.state()
            if state.current != stage or state.status != "pending_approval":
                raise ValueError("Decisions are accepted only for the currently pending stage")
            output = self._load(state, stage)
            if expected_digest is not None and digest(output) != expected_digest:
                raise ValueError("Review is stale; reload the current artifact before approving")
            if approve:
                apply_selection(stage, output, selected_id)
            elif not feedback.strip():
                raise ValueError("Rejection requires --feedback")
            state.approvals[stage] = Decision(
                stage=stage,
                status="approved" if approve else "rejected",
                artifact_digest=digest(output),
                reviewer=reviewer,
                selected_id=selected_id,
                feedback=feedback,
                decided_at=now(),
            )
            state.status = "ready" if approve else "rejected"
            self._save(state)

    def revise(self, stage: Stage, feedback: str):
        if not feedback.strip():
            raise ValueError("Revision requires --feedback")
        with run_lock(self.root):
            state = self.state()
            if stage not in state.checkpoints and state.current != stage:
                raise ValueError("Cannot revise a stage that has not run")
            for downstream in STAGES[STAGES.index(stage) :]:
                state.checkpoints.pop(downstream, None)
                state.approvals.pop(downstream, None)
                self.checkpoint_path(downstream).unlink(missing_ok=True)
                folder = self.root / "assets" / downstream
                if folder.exists():
                    shutil.rmtree(folder)
            for filename in ("result.json", "final.mp4", "final.demo.mp4", "timeline.json"):
                (self.root / filename).unlink(missing_ok=True)
            state.feedback[stage] = feedback
            state.current = stage
            state.status = "ready"
            state.last_error = None
            self._save(state)
