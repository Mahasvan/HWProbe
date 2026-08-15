from hwprobe.core.windows.common import format_acpi_path, format_pci_path
from hwprobe.interops.win.bindings.gpu_info import GPURaw, get_gpu_info
from hwprobe.models.gpu_models import GPUInfo, GraphicsInfo
from hwprobe.models.size_models import Megabyte
from hwprobe.models.status_models import StatusType
from hwprobe.util.location_paths import fetch_pcie_info, get_location_paths

_VENDOR_NAMES = {
    0x10DE: "NVIDIA",
    0x1002: "AMD",
    0x8086: "Intel",
}


def _map_gpu(raw: GPURaw) -> GPUInfo:
    gpu = GPUInfo()
    gpu.name = raw.name
    gpu.manufacturer = _VENDOR_NAMES.get(raw.vendor_id, f"Not Recognized (0x{raw.vendor_id:04X})")
    gpu.vendor_id = f"0x{raw.vendor_id:04X}"
    gpu.device_id = f"0x{raw.device_id:04X}"

    # Subsystem ID: DXGI gives a single uint32 — high 16 = vendor, low 16 = device
    gpu.subsystem_manufacturer = f"0x{(raw.subsystem_id >> 16) & 0xFFFF:04X}"
    gpu.subsystem_model = f"0x{raw.subsystem_id & 0xFFFF:04X}"

    # Location paths + PCIe: reuse util.location_paths (cfgmgr32 via ctypes)
    if raw.pnp_device_id:
        paths = get_location_paths(raw.pnp_device_id)
        if paths:
            for path in paths:
                if path.startswith("ACPI") and not gpu.acpi_path:
                    gpu.acpi_path = format_acpi_path(path)
                if path.startswith("PCIROOT") and not gpu.pci_path:
                    gpu.pci_path = format_pci_path(path)

        pcie = fetch_pcie_info(raw.pnp_device_id)
        if pcie:
            speed, width = pcie
            gpu.pcie_link.gen.current = speed
            gpu.pcie_link.width.current = width

    # VRAM: registry fallback wins if present, else DXGI value
    vram_bytes = raw.vram_bytes or raw.dedicated_video_memory_bytes
    if vram_bytes > 0:
        gpu.vram = Megabyte(capacity=int(vram_bytes) // (1024 * 1024))

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
