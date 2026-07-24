from typing import Literal

from pydantic import BaseModel, Field


class ConsentCreate(BaseModel):
    subject_name: str = Field(min_length=1, max_length=120)
    likeness_confirmed: bool
    voice_confirmed: bool
    rights_confirmed: bool


class ProjectCreate(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    script: str = Field(min_length=1, max_length=20_000)
    output_format: Literal["vertical", "landscape", "square"] = "vertical"
    consent_id: str


class JobCreate(BaseModel):
    engine: Literal["proof_render", "external_clone"] = "proof_render"


class ApprovalCreate(BaseModel):
    decision: Literal["approved", "rejected"]
    note: str | None = Field(default=None, max_length=2000)


class WorkerClaim(BaseModel):
    worker_id: str = Field(min_length=1, max_length=120)


class WorkerComplete(BaseModel):
    status: Literal["completed", "failed"]
    output_path: str | None = None
    error: str | None = None
