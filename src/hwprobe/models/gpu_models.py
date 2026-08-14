from typing import Optional

from pydantic import BaseModel, Field

from hwprobe.models.component_model import ComponentInfo
from hwprobe.models.size_models import StorageSize


class AppleExtendedGPUInfo(BaseModel):
    """Contains extra information about Apple Silicon GPUs."""

    #: Number of GPU cores.
    gpu_core_count: Optional[int] = None

    #: Number of GPU Performance Shaders
    performance_shader_count: Optional[int] = None

    #: GPU Generation
    gpu_gen: Optional[int] = None


class PCIeLinkValue(BaseModel):
    """The max/current value distinction for a PCIe Link"""
    max: Optional[int] = None
    current: Optional[int] = None

class PCIeLinkInfo(BaseModel):
    """Information about the PCIe Link for this GPU (gen/width)"""
    gen: Optional[PCIeLinkValue] = None
    width: Optional[PCIeLinkValue] = None


class GPUInfo(BaseModel):
    """Information for one GPU is stored here"""

    name: Optional[str] = None

    #: This is the hexadecimal number that identifies the manufacturer of the GPU.
    #: Format: ``0x10DE`` - Nvidia
    vendor_id: Optional[str] = None

    #: This is the hexadecimal number that identifies the GPU model.
    #: Format: ``0xPQRS``
    device_id: Optional[str] = None

    #: GPU vendor. ``NVIDIA``, for example.
    manufacturer: Optional[str] = None

    #: The manufacturer of the GPU. For example, it may be ``Lenovo`` on a Thinkpad.
    subsystem_manufacturer: Optional[str] = None

    #: The model name given by the subsystem manufacturer.
    subsystem_model: Optional[str] = None

    #: ACPI device path, e.g. ``\\_SB.PC00.RP05.PXSX``.
    acpi_path: Optional[str] = None
    #: PCI path from the firmware tree, e.g. ``PciRoot(0x0)/Pci(0x1C,0x5)/Pci(0x0,0x0)``.
    pci_path: Optional[str] = None

    #: Number of lanes that the GPU occupies on the PCIe bus.
    pcie_link: Optional[PCIeLinkInfo] = None

    #: Total VRAM available on the GPU.
    vram: Optional[StorageSize] = None

    #: Only for Apple Silicon GPUs. ``null`` on all other platforms and GPUs.
    apple_gpu_info: Optional[AppleExtendedGPUInfo] = None


class GraphicsInfo(ComponentInfo):
    """Contains list of ``GPUInfo`` objects."""

    #: List of GPU modules present in the system.
    modules: list[GPUInfo] = Field(default_factory=list)
