from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import SourceType


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    source_type: SourceType

    @field_validator("name")
    @classmethod
    def _reject_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("A project needs a name.")
        return stripped


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    source_type: SourceType
    schema_name: str | None
    table_count: int | None
    is_demo: bool
    created_at: datetime
