"""
Python bindings for Linux GPU info via C library.
Uses ctypes to interface with libdevice_info.so
"""

import ctypes
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class GPUProperties:
    """Python representation of the C GPUProperties struct"""

    name: str
    vendor_id: int
    device_id: int
    vram_total_mb: int
    vram_used_mb: int
    pcie_gen: int
    pcie_width: int
    pci_slot: str
    driver: str


class _CGPUProperties(ctypes.Structure):
    """C struct layout matching gpu_info.h"""

    _fields_ = [
        ("name", ctypes.c_char * 256),
        ("vendor_id", ctypes.c_uint32),
        ("device_id", ctypes.c_uint32),
        ("vram_total_mb", ctypes.c_uint64),
        ("vram_used_mb", ctypes.c_uint64),
        ("pcie_gen", ctypes.c_int),
        ("pcie_width", ctypes.c_int),
        ("pci_slot", ctypes.c_char * 32),
        ("driver", ctypes.c_char * 64),
    ]


def _find_library() -> Optional[ctypes.CDLL]:
    """Locate and load libdevice_info.so"""
    # Try relative to this file first
    _HERE = Path(__file__).parent
    _LIB_PATH = _HERE / "libdevice_info.so"

    if not _LIB_PATH.exists():
        return None

    try:
        lib = ctypes.CDLL(str(_LIB_PATH))
        # Configure function signature
        lib.get_gpu_info.argtypes = [ctypes.POINTER(_CGPUProperties), ctypes.c_int]
        lib.get_gpu_info.restype = ctypes.c_int
        return lib
    except (OSError, AttributeError):
        return None


# Module-level library handle
_lib = _find_library()


def is_available() -> bool:
    """Check if the native library is available"""
    return _lib is not None


def get_gpu_info(max_gpus: int = 16) -> list[GPUProperties]:
    """
    Query GPU information via native C library.

    Args:
        max_gpus: Maximum number of GPUs to detect (default 16)

    Returns:
        List of GPUProperties objects, one per detected GPU

    Raises:
        RuntimeError: If the library is not available or the call fails
    """
    if not _lib:
        raise RuntimeError("libdevice_info.so not found. Build the C library first.")

    # Allocate array of C structs
    gpu_array = (_CGPUProperties * max_gpus)()

    # Call C function
    count = _lib.get_gpu_info(ctypes.cast(gpu_array, ctypes.POINTER(_CGPUProperties)), max_gpus)

    if count < 0:
        raise RuntimeError("get_gpu_info() failed")

    # Convert C structs to Python dataclasses
    result = []
    for i in range(count):
        g = gpu_array[i]
        result.append(
            GPUProperties(
                name=g.name.decode("utf-8", errors="replace").strip(),
                vendor_id=g.vendor_id,
                device_id=g.device_id,
                vram_total_mb=g.vram_total_mb,
                vram_used_mb=g.vram_used_mb,
                pcie_gen=g.pcie_gen if g.pcie_gen > 0 else 0,
                pcie_width=g.pcie_width if g.pcie_width > 0 else 0,
                pci_slot=g.pci_slot.decode("utf-8", errors="replace").strip(),
                driver=g.driver.decode("utf-8", errors="replace").strip(),
            )
        )

    return result
