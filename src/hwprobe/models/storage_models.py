from typing import Optional

from pydantic import BaseModel, Field

from hwprobe.models.component_model import ComponentInfo
from hwprobe.models.size_models import StorageSize


class DiskInfo(BaseModel):
    #: Device Name
    model: Optional[str] = None

    manufacturer: Optional[str] = None

    #: Unique identifier assigned by the OS - ``disk0``/``sda``, etc.
    identifier: Optional[str] = None

    #: Internal/External
    location: Optional[str] = None

    #: PCIe/SCSI/etc.
    connector: Optional[str] = None

    #: HDD/SSD/eMMC/SD/etc.
    type: Optional[str] = None

    #: Note: For eMMC Storage devices in Linux, this ID is the JEDEC Standard Manufacturer’s Identification Code.
    vendor_id: Optional[str] = None

    device_id: Optional[str] = None

    size: Optional[StorageSize] = None


class StorageInfo(ComponentInfo):
    modules: list[DiskInfo] = Field(default_factory=list)
