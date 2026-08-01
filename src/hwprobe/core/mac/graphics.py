from typing import List

from hwprobe.models.gpu_models import GraphicsInfo, GPUInfo, AppleExtendedGPUInfo
from hwprobe.models.size_models import Megabyte
from hwprobe.models.status_models import StatusType

_VENDOR_MAP = {
    0x106B: "Apple Inc.",
    0x10DE: "Nvidia",
    0x1002: "AMD",
    0x8086: "Intel",
}

"""
This module fetches graphics information on macOS using a C++ extension that interfaces with IOKit. 
Refer interops/mac/bindings/gpu_info.py for the C++ extension implementation.
"""


def fetch_graphics_info() -> GraphicsInfo:
    graphics_info = GraphicsInfo()

    # The binding raises FileNotFoundError at import time if libdevice_info.dylib is missing,
    # and RuntimeError at call time if the C library returns -1
    try:
        from hwprobe.interops.mac.bindings.gpu_info import get_gpu_info, GPUProperties
        gpu_list: List[GPUProperties] = get_gpu_info()

    except FileNotFoundError as e:
        graphics_info.status.type = StatusType.FAILED
        graphics_info.status.messages.append(f"libdevice_info.dylib not found – rebuild the CMake project: {e}")
        return graphics_info

    except RuntimeError as e:
        # get_gpu_info() returns -1 when IOKit enumeration fails
        graphics_info.status.type = StatusType.FAILED
        graphics_info.status.messages.append(f"IOKit GPU enumeration failed: {e}")
        return graphics_info

    except Exception as e:
        graphics_info.status.type = StatusType.FAILED
        graphics_info.status.messages.append(f"Unexpected error loading GPU binding: {e}")
        return graphics_info

    for gpu in gpu_list:
        module = GPUInfo()

        module.name = gpu.name.strip() if gpu.name and gpu.name.strip() else None
        if not module.name:
            graphics_info.status.make_partial("Could not get GPU name")

        if gpu.vendor_id:
            module.vendor_id = hex(gpu.vendor_id)
            module.manufacturer = _VENDOR_MAP.get(gpu.vendor_id, "Unknown")
        else:
            graphics_info.status.make_partial(
                f"Could not get vendor ID for GPU: {module.name}"
            )

        # Apple Silicon GPUs report 0x0000 for device_id. Flag it as partial for non-Apple-Silicon GPUs.
        if gpu.device_id:
            module.device_id = hex(gpu.device_id)
        elif not gpu.is_apple_silicon:
            graphics_info.status.make_partial(f"Could not get device ID for GPU: {module.name}")

        if gpu.acpi_path:
            module.acpi_path = gpu.acpi_path
        if gpu.pci_path:
            module.pci_path = gpu.pci_path

        # VRAM for non-Apple-Silicon GPUs
        # Apple Silicon GPUs can use the entire system memory as VRAM
        if not gpu.is_apple_silicon and gpu.vram_mb:
            module.vram = Megabyte(capacity=gpu.vram_mb)
        elif not gpu.is_apple_silicon:
            # Non-Apple Silicon GPU, and yet VRAM is reported as 0 MB.
            graphics_info.status.make_partial(f"Could not get VRAM for non-Apple-Silicon GPU: {module.name}")

        # Apple Silicon extended info
        if gpu.is_apple_silicon:
            if gpu.apple_gpu is None:
                graphics_info.status.make_partial(
                    f"Apple Silicon GPU detected but extended properties are unavailable for: {module.name}"
                )
            else:
                if gpu.apple_gpu.unified_memory_mb:
                    module.vram = Megabyte(capacity=gpu.apple_gpu.unified_memory_mb)
                else:
                    graphics_info.status.make_partial(
                        f"Apple Silicon GPU reported 0 MB unified memory for: {module.name}"
                    )

                apple_info = AppleExtendedGPUInfo()
                apple_info.gpu_core_count = gpu.apple_gpu.core_count
                apple_info.performance_shader_count = gpu.apple_gpu.gpu_perf_shaders
                apple_info.gpu_gen = gpu.apple_gpu.gpu_gen
                module.apple_gpu_info = apple_info

        graphics_info.modules.append(module)

    return graphics_info

