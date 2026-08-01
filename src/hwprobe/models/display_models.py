from typing import Optional

from pydantic import BaseModel, Field

from hwprobe.models.component_model import ComponentInfo


class ResolutionInfo(BaseModel):
    """Resolution information for a Display."""

    #: Horizontal resolution in pixels.
    width: Optional[int] = None
    #: Vertical resolution in pixels.
    height: Optional[int] = None
    #: Refresh rate in Hz.
    refresh_rate: Optional[float] = None
    #: Bit depth (bits per channel).
    bit_depth: Optional[int] = None


class DisplayModuleInfo(BaseModel):
    """Information for one Display is stored here"""

    name: Optional[str] = None

    #: Year it was manufactured / designed.
    year: Optional[int] = None

    #: ACPI path of the display device.
    acpi_path: Optional[str] = None

    #: PCI path of the device
    pci_path: Optional[str] = None

    #: Parent GPU driving this display
    gpu_name: Optional[str] = None

    resolution: Optional[ResolutionInfo] = None

    # Display Interface (HDMI, DP, VGA, etc.) - enum: DISPLAY_CON_TYPE
    interface: Optional[str] = None

    # Serial Number
    serial_number: Optional[str] = None

    #: Three-letter code assigned to each manufacturer.
    manufacturer_code: Optional[str] = None


class DisplayInfo(ComponentInfo):
    """Contains a list of ``DisplayModuleInfo`` objects."""

    #: List of GPU modules present in the system.
    modules: list[DisplayModuleInfo] = Field(default_factory=list)
