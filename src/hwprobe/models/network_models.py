from typing import Optional

from hwprobe.models.component_model import ComponentInfo
from pydantic import BaseModel, Field


class NICInfo(BaseModel):
    name: Optional[str] = None

    # TODO: Old Stuff: Need to revamp
    device_id: Optional[str] = None

    vendor_id: Optional[str] = None

    #: ACPI device path, e.g. ``\\_SB.PC00.RP05.PXSX``.
    acpi_path: Optional[str] = None

    #: PCI path from the firmware tree, e.g. ``PciRoot(0x0)/Pci(0x1C,0x5)/Pci(0x0,0x0)``.
    pci_path: Optional[str] = None

    manufacturer: Optional[str] = None

    """New Stuff begins here"""
    #: BSD Device Name for Linux/macOS, Example: ``en0``
    interface: Optional[str] = None
    mac_address: Optional[str] = None
    type: Optional[str] = None
    ip_address: Optional[str] = None


class NetworkInfo(ComponentInfo):
    modules: list[NICInfo] = Field(default_factory=list)
