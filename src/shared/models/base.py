from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class TimestampedModel(BaseModel):
    """Base model with creation and update timestamps."""

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    model_config = ConfigDict(from_attributes=True)


class UUIDModel(BaseModel):
    """Base model with UUID primary key."""

    id: UUID = Field(default_factory=uuid4)

    model_config = ConfigDict(from_attributes=True)


class BaseEntity(UUIDModel, TimestampedModel):
    """Base entity combining UUID and timestamps."""

    model_config = ConfigDict(from_attributes=True)
