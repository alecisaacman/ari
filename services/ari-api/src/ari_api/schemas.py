from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class APIModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class NoteCreateRequest(APIModel):
    title: str
    content: str


class TaskCreateRequest(APIModel):
    title: str
    notes: str = ""


class MemoryCreateRequest(APIModel):
    type: str
    title: str
    content: str
    tags: list[str] = Field(default_factory=list)


class CoordinationUpsertRequest(APIModel):
    payload: dict[str, Any]


class PolicyPayloadRequest(APIModel):
    payload: dict[str, Any] = Field(default_factory=dict)


class OrchestrationClassifyRequest(APIModel):
    rawOutput: str
    currentPriority: str = ""
    latestDecision: str = ""


class ProjectDraftRequest(APIModel):
    goal: str
    source: Literal["goal", "active_project", "manual"] = "manual"
