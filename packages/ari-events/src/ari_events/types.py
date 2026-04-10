from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class NormalizedInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str
    occurred_at: datetime
    title: str
    body: str = ""
    normalized_text: str = ""
    payload: dict[str, object] = Field(default_factory=dict)
