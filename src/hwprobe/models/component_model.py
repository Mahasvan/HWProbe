from pydantic import BaseModel, Field

from hwprobe.models.status_models import Status


class ComponentInfo(BaseModel):
    # Each component gets its own fresh status object
    status: Status = Field(default_factory=lambda: Status())
