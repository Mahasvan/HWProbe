"""
Python bindings for Linux GPU info via C library.
Uses ctypes to interface with libdevice_info.so
"""

import ctypes
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path
from typing import Optional


class GPUInfoQueryStatus(IntEnum):
    FAILURE = -1
    DRM_SUCCESS = 0
    VULKAN_VRAM_FALLBACK = 1
    VULKAN_NAME_FALLBACK = 2


@dataclass
class GPUProperties:
    """Python representation of the C GPUProperties struct"""

    name: str
    vram_total_mb: int
    vram_used_mb: int


class _CGPUProperties(ctypes.Structure):
    """C struct layout matching gpu_info.h"""

    _fields_ = [
        ("name", ctypes.c_char * 256),
        ("vram_total_mb", ctypes.c_uint64),
        ("vram_used_mb", ctypes.c_uint64),
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
        lib.get_gpu_info.argtypes = [ctypes.c_char_p, ctypes.c_uint32, ctypes.POINTER(_CGPUProperties)]
        lib.get_gpu_info.restype = GPUInfoQueryStatus
        return lib
    except (OSError, AttributeError):
        return None


# Module-level library handle
_lib = _find_library()


def is_available() -> bool:
    """Check if the native library is available"""
    return _lib is not None


def get_gpu_info(bdf: str, vendor_id: int) -> tuple[GPUInfoQueryStatus, GPUProperties]:
    """
    Query VRAM and driver name for the GPU at the given PCI BDF address.

    Args:
        bdf: PCI address in ``domain:bus:device.function`` form, e.g. ``0000:01:00.0``
        vendor_id: PCI vendor ID (e.g. ``0x1002`` for AMD, ``0x8086`` for Intel)

    Returns:
        A GPUProperties object with VRAM figures and DRM driver name

    Raises:
        RuntimeError: If the library is not available or the underlying C call fails
    """
    if not _lib:
        raise RuntimeError("libdevice_info.so not found. Build the C library first.")

    c_gpu = _CGPUProperties()
    ret = _lib.get_gpu_info(bdf.encode(), vendor_id, ctypes.byref(c_gpu))

    return (
        ret,
        GPUProperties(
            name=c_gpu.name.decode("utf-8", errors="replace").strip(),
            vram_total_mb=c_gpu.vram_total_mb,
            vram_used_mb=c_gpu.vram_used_mb,
        ),
    )
