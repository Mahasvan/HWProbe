from hwprobe.interops.win.bindings.gpu_info import GPUProperties, get_gpu_info
from hwprobe.models.gpu_models import GPUInfo, GraphicsInfo
from hwprobe.models.size_models import Megabyte
from hwprobe.models.status_models import StatusType


def _map_gpu(raw: GPUProperties) -> GPUInfo:
    gpu = GPUInfo()
    gpu.name = raw.name
    gpu.manufacturer = raw.manufacturer
    gpu.vendor_id = f"0x{raw.vendor_id:04X}"
    gpu.device_id = f"0x{raw.device_id:04X}"
    gpu.subsystem_manufacturer = f"0x{raw.subsystem_vendor_id:04X}"
    gpu.subsystem_model = f"0x{raw.subsystem_device_id:04X}"
    gpu.acpi_path = raw.acpi_path
    gpu.pci_path = raw.pci_path
    gpu.pcie_gen = raw.pcie_gen if raw.pcie_gen else None
    gpu.pcie_width = raw.pcie_width if raw.pcie_width else None
    if raw.vram_mb > 0:
        gpu.vram = Megabyte(capacity=int(raw.vram_mb))
    return gpu


def fetch_graphics_info() -> GraphicsInfo:
    graphics_info = GraphicsInfo()

    try:
        raw_gpus = get_gpu_info()
    except RuntimeError as e:
        graphics_info.status.type = StatusType.FAILED
        graphics_info.status.messages.append(str(e))
        return graphics_info

    if not raw_gpus:
        graphics_info.status.type = StatusType.FAILED
        graphics_info.status.messages.append("No GPUs found")
        return graphics_info

    for raw in raw_gpus:
        graphics_info.modules.append(_map_gpu(raw))

    return graphics_info
