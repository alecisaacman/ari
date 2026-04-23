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


class ExecutionCommandRequest(APIModel):
    command: str
    cwd: str = "."
    timeoutSeconds: int = 60


class ExecutionReadFileRequest(APIModel):
    path: str


class ExecutionWriteFileRequest(APIModel):
    path: str
    content: str
    actionId: str | None = None


class ExecutionPatchFileRequest(APIModel):
    path: str
    find: str
    replace: str
    actionId: str | None = None


class ExecutionGoalRequest(APIModel):
    goal: str
    maxCycles: int = 1
    planner: Literal["rule_based", "model"] = "rule_based"


class CodingOperation(APIModel):
    type: Literal["write", "patch"]
    path: str
    content: str | None = None
    find: str | None = None
    replace: str | None = None


class CodingActionCreateRequest(APIModel):
    title: str
    summary: str = ""
    operations: list[CodingOperation] = Field(default_factory=list)
    verifyCommand: str = ""
    workingDirectory: str = "."
    approvalRequired: bool | None = None
