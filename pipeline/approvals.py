"""Human decisions are explicit and bound to the reviewed artifact digest."""

from datetime import datetime, timezone
from typing import Literal

from pydantic import field_validator

from pipeline.models import Identifier, Model, Stage, Text


class PendingApproval(Exception):
    pass


class RejectedApproval(ValueError):
    pass


class Decision(Model):
    stage: Stage
    status: Literal["approved", "rejected"]
    artifact_digest: Text
    reviewer: Text
    selected_id: Identifier | None = None
    feedback: str = ""
    decided_at: Text

    @field_validator("reviewer")
    @classmethod
    def reviewer_not_blank(cls, value):
        if not value.strip():
            raise ValueError("Reviewer name cannot be blank")
        return value.strip()


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def apply_selection(stage: str, output: Model, selected_id: str | None) -> Model:
    payload = output.model_dump(mode="json")
    if stage in ("pesquisa_titulos", "thumbnail"):
        key = "research" if stage == "pesquisa_titulos" else "thumbnail"
        if not selected_id:
            raise ValueError(f"Select a candidate ID to approve {stage}")
        payload[key]["selected_id"] = selected_id
    elif selected_id:
        raise ValueError("--select applies only to titles and thumbnails")
    return type(output).model_validate(payload)


def review_text(stage: str, output: Model, root) -> str:
    lines = [f"\nReview required: {stage}"]
    if stage == "pesquisa_titulos":
        lines += [
            f"{c.id}: {c.title}\n  {c.angle}\n  {c.rationale}" for c in output.research.candidates
        ]
    elif stage == "thumbnail":
        lines += [
            f"{c.id}: {root / c.image.path}\n  {c.prompt}" for c in output.thumbnail.candidates
        ]
    else:
        lines.append(f"Inspect {root / 'checkpoints' / (stage + '.json')}")
    lines.append("Approval requires reviewing the files; no default selection is applied.")
    return "\n".join(lines)
