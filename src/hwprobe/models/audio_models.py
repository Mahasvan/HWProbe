from typing import Optional

from hwprobe.models.component_model import ComponentInfo, BaseModel
from pydantic import Field


# Also known as an audio endpoint
class AudioDeviceInfo(BaseModel):
    """This model holds information about an audio device (endpoint)."""

    #: The name of the audio device
    name: Optional[str] = None

    #: The data flow type of the audio device, e.g., 'Render', 'Capture', etc.
    data_flow: Optional[str] = None

    #: The PNP Device ID of the parent audio controller
    parent_pnp_device_id: Optional[str] = None


class AudioControllerInfo(BaseModel):
    """This model holds information about an audio controller device."""

    #: The name of the audio controller
    name: Optional[str] = None

    #: The PNP Device ID of the audio controller
    pnp_device_id: Optional[str] = None

    #: The manufacturer of the audio controller
    manufacturer: Optional[str] = None

    #: The list of audio endpoints associated with this controller
    endpoints: list[AudioDeviceInfo] = Field(default_factory=list)


class AudioInfo(ComponentInfo):
    """This is the model that holds audio information."""

    #: The list of audio controllers / modules present on the system
    modules: list[AudioControllerInfo] = Field(default_factory=list)
