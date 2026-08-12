import os
from typing import Optional

from hwprobe.core.linux.common import PCI_ROOT_PATH, ACPIResult, _read_from_sysfs, pci_path_linux, _resolve_acpi_path
from hwprobe.models.gpu_models import GPUInfo, GraphicsInfo
from hwprobe.models.size_models import Megabyte
from hwprobe.models.status_models import StatusType

# Try to import native C library bindings
try:
    from hwprobe.interops.linux.bindings import gpu_info as native_gpu

    NATIVE_AVAILABLE = native_gpu.is_available()
except (ImportError, RuntimeError) as e:
    NATIVE_AVAILABLE = False

# Currently, the info in /sys/class/drm/cardX is being used.
# TODO: Check if lspci and lshw -c display can be used
# Answer: nope, pciutils and lshw are not guaranteed to be installed on all systems.
# https://unix.stackexchange.com/questions/393/how-to-check-how-many-lanes-are-used-by-the-pcie-card
#  ^ Solution: /sys/bus/pci/devices/{...}/current_link_width

DISPLAY_CONTROLLER_CLASS = 0x03  # Display Controller class code in PCI

def _pcie_gen(raw_speed: str) -> Optional[int]:
    # Path example: /sys/bus/pci/devices/0000:03:00.0/max_link_speed

    # Mapping Dictionary
    speed_to_gen = {"2.5 GT/s": 1, "5.0 GT/s": 2, "8.0 GT/s": 3, "16.0 GT/s": 4, "32.0 GT/s": 5, "64.0 GT/s": 6}

    for k, v in speed_to_gen.items():
        """ `8.0 GT/s PCIe` may be a possible candidate, so we dont use direct matching"""
        if k in raw_speed:
            return v

    return None


def _check_gpu_class(device: str) -> bool:
    """
    The class code is three hex-bytes, where the leftmost hex-byte is the base class
    We want the devices of base class 0x03, which denotes a Display Controller.
    """
    device_class = _read_from_sysfs(PCI_ROOT_PATH, device, "class")
    class_code = int(device_class, base=16)
    base_class = class_code >> 16

    return base_class == DISPLAY_CONTROLLER_CLASS

def fetch_graphics_info() -> GraphicsInfo:
    graphics_info = GraphicsInfo()

    if not posixpath.exists(PCI_ROOT_PATH):
        graphics_info.status.type = StatusType.FAILED
        graphics_info.status.messages.append("/sys/bus/pci/devices/ not found")
        return graphics_info

    for device in os.listdir(PCI_ROOT_PATH):
        try:
            if not _check_gpu_class(device):
                continue
        except Exception as e:
            graphics_info.status.type = StatusType.PARTIAL
            graphics_info.status.messages.append(f"Could not open file for {device}: {e}")
            continue

        gpu = GPUInfo()
        gpu_path = posixpath.join(PCI_ROOT_PATH, device)

        if (vendor_id := _read_from_sysfs(gpu_path, "vendor")) is not None:
            gpu.vendor_id = vendor_id
        else:
            graphics_info.status.type = StatusType.PARTIAL
            graphics_info.status.messages.append(f"Could not read vendor ID for {device}")


        if (device_id := _read_from_sysfs(gpu_path, "device")) is not None:
            gpu.device_id = device_id
        else:
            graphics_info.status.type = StatusType.PARTIAL
            graphics_info.status.messages.append(f"Could not read device ID for {device}")


        if (cur_width := _read_from_sysfs(gpu_path, "current_link_width")) is not None:
            if cur_width.isnumeric() and int(cur_width) > 0:
                gpu.current_pcie_width = int(cur_width)
        else:
            graphics_info.status.type = StatusType.PARTIAL
            graphics_info.status.messages.append(f"Could not read current link width for {device}")

        if (max_width := _read_from_sysfs(gpu_path, "max_link_width")) is not None:
            if max_width.isnumeric() and int(max_width) > 0:
                gpu.max_pcie_width = int(max_width)
        else:
            graphics_info.status.type = StatusType.PARTIAL
            graphics_info.status.messages.append(f"Could not read max link width for {device}")


        if (cur_pcie_speed := _read_from_sysfs(gpu_path, "current_link_speed")) is not None:
            if cur_pcie_speed:
                gpu.current_pcie_gen = _pcie_gen(cur_pcie_speed)
        else:
            graphics_info.status.type = StatusType.PARTIAL
            graphics_info.status.messages.append(f"Could not read current link speed for {device}")


        if (max_pcie_speed := _read_from_sysfs(gpu_path, "max_link_speed")) is not None:
            if max_pcie_speed:
                gpu.max_pcie_gen = _pcie_gen(max_pcie_speed)
        else:
            graphics_info.status.type = StatusType.PARTIAL
            graphics_info.status.messages.append(f"Could not read max link speed for {device}")


        acpi_path, result = _resolve_acpi_path(device)
        if result == ACPIResult.SUCCESS or result == ACPIResult.INFERRED:
            gpu.acpi_path = acpi_path
            
            if result == ACPIResult.INFERRED:
                graphics_info.status.messages.append(f"ACPI path for {device} was inferred through parent device (bridge), may be inaccurate")
        else:
            graphics_info.status.type = StatusType.PARTIAL
            graphics_info.status.messages.append(f"Could not read ACPI path for {device}")


        if (pci_path := pci_path_linux(device)) is not None:
            gpu.pci_path = pci_path
        else:
            graphics_info.status.type = StatusType.PARTIAL
            graphics_info.status.messages.append(f"Could not resolve PCI path for {device}")

        if (
            vendor_id is not None and 
            NATIVE_AVAILABLE is True and 
            (native := native_gpu.get_gpu_info(device, int(gpu.vendor_id, 16))) is not None
        ):
            gpu.name = native.name
            if native.vram_total_mb > 0:
                gpu.vram = Megabyte(capacity=int(native.vram_total_mb))
        

        graphics_info.modules.append(gpu)

    return graphics_info
