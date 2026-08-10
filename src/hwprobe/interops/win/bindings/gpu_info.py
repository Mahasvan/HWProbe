"""
gpu_info.py  -  Python ctypes binding for gpu_info.dll (raw GPU data)

Returns raw values from DXGI + SetupAPI + registry. All parsing/derivation is
done in the consumer (core/windows/graphics.py): subsystem ID split, location
paths, PCIe info, manufacturer name, VRAM unit conversion.

Usage:
    from hwprobe.interops.win.bindings.gpu_info import get_gpu_info
    gpus = get_gpu_info()
    for g in gpus:
        print(g.name, hex(g.vendor_id), g.pnp_device_id)

Source: interops/win/include/gpu_info.h and interops/win/src/gpu_info.cpp.
"""

import ctypes
import pathlib
from dataclasses import dataclass
from typing import Optional

_HERE = pathlib.Path(__file__).parent
_LIB_PATH = _HERE / "gpu_info.dll"

if not _LIB_PATH.exists():
    raise FileNotFoundError(
        f"gpu_info.dll not found at {_LIB_PATH}.\nBuild the project first:  cmake --build build --config Release"
    )

_lib = ctypes.WinDLL(str(_LIB_PATH))


# ---- mirror the C struct ----


class _WinGPURaw(ctypes.Structure):
    _fields_ = [
        ("name", ctypes.c_char * 256),
        ("vendor_id", ctypes.c_uint32),
        ("device_id", ctypes.c_uint32),
        ("subsystem_id", ctypes.c_uint32),
        ("dedicated_video_memory_bytes", ctypes.c_uint64),
        ("pnp_device_id", ctypes.c_char * 512),
        ("vram_bytes", ctypes.c_uint64),
    ]


_lib.get_gpu_info.restype = ctypes.c_int
_lib.get_gpu_info.argtypes = [ctypes.POINTER(_WinGPURaw), ctypes.c_int]


# ---- Python-facing dataclass (raw values, no parsing) ----


@dataclass
class GPURaw:
    name: str
    vendor_id: int
    device_id: int
    subsystem_id: int
    dedicated_video_memory_bytes: int
    pnp_device_id: Optional[str]
    vram_bytes: int


# ---- public API ----

_MAX_GPUS = 8


def get_gpu_info() -> list[GPURaw]:
    """Return a list of GPURaw for every GPU found on this machine."""
    buf = (_WinGPURaw * _MAX_GPUS)()
    count = _lib.get_gpu_info(buf, _MAX_GPUS)
    if count < 0:
        raise RuntimeError("get_gpu_info() failed (C library returned -1)")

    result = []
    for i in range(count):
        raw = buf[i]
        pnp = raw.pnp_device_id.decode("utf-8", errors="replace").strip("\x00") or None
        result.append(
            GPURaw(
                name=raw.name.decode("utf-8", errors="replace").strip("\x00"),
                vendor_id=raw.vendor_id,
                device_id=raw.device_id,
                subsystem_id=raw.subsystem_id,
                dedicated_video_memory_bytes=raw.dedicated_video_memory_bytes,
                pnp_device_id=pnp,
                vram_bytes=raw.vram_bytes,
            )
        )
    return result


if __name__ == "__main__":
    gpus = get_gpu_info()
    print(f"Found {len(gpus)} GPU(s):\n")
    for idx, g in enumerate(gpus):
        print(f"GPU {idx}:")
        print(f"  Name:              {g.name}")
        print(f"  Vendor ID:         0x{g.vendor_id:04X}")
        print(f"  Device ID:         0x{g.device_id:04X}")
        print(f"  Subsystem ID:      0x{g.subsystem_id:08X}")
        print(f"  Dedicated VRAM:    {g.dedicated_video_memory_bytes} bytes")
        if g.pnp_device_id:
            print(f"  PNP Device ID:     {g.pnp_device_id}")
        if g.vram_bytes:
            print(f"  Registry VRAM:     {g.vram_bytes} bytes")
        print()
