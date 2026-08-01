from typing import Optional

from pydantic import BaseModel, Field

from hwprobe.models.component_model import ComponentInfo
from hwprobe.models.size_models import StorageSize


class MemoryModuleSlot(BaseModel):
    channel: str = ""
    bank: str = ""


class MemoryModuleInfo(BaseModel):
    #: Hynix/Micron, etc.
    manufacturer: Optional[str] = None

    #: Manufacturer-assigned part number
    part_number: Optional[str] = None

    #: DDR4/DDR5/etc.
    type: Optional[str] = None
    capacity: Optional[StorageSize] = None
    frequency_mhz: Optional[int] = None
    slot: Optional[MemoryModuleSlot] = None

    #: Error-Correcting Code (ECC) support.
    supports_ecc: Optional[bool] = None
    ecc_type: Optional[str] = None


class MemoryInfo(ComponentInfo):
    modules: list[MemoryModuleInfo] = Field(default_factory=list)
