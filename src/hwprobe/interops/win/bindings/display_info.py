"""
display_info.py  -  Python ctypes binding for display_info.dll

Two exports:
  - get_display_devices(): user32 + CCD + DXGI in one pass — all display info
  - get_edid(): SetupAPI + registry EDID lookup — raw EDID bytes

All Win32 calls live in C++ — Python only does EDID parsing and data assembly.

Usage:
    from hwprobe.interops.win.bindings.display_info import (
        get_display_devices, get_edid,
    )

Source: interops/win/include/display_info.h and interops/win/src/display_info.cpp.
"""

import ctypes
import pathlib
from dataclasses import dataclass
from typing import Optional

_HERE = pathlib.Path(__file__).parent
_LIB_PATH = _HERE / "display_info.dll"

if not _LIB_PATH.exists():
    raise FileNotFoundError(
        f"display_info.dll not found at {_LIB_PATH}.\n"
        f"Build the project first:  cmake --build build --config Release"
    )

_lib = ctypes.WinDLL(str(_LIB_PATH))


# ---- mirror the C struct ----

class _DisplayDeviceInfo(ctypes.Structure):
    _fields_ = [
        ("device_id", ctypes.c_char * 32),
        ("pnp_device_id", ctypes.c_char * 128),
        ("monitor_name", ctypes.c_char * 128),
        ("display_path", ctypes.c_char * 512),
        ("gpu_name", ctypes.c_char * 256),
        ("width", ctypes.c_int),
        ("height", ctypes.c_int),
        ("refresh_rate", ctypes.c_int),
        ("output_technology", ctypes.c_int),
    ]


# ---- function signatures ----

_lib.get_display_devices.restype = ctypes.c_int
_lib.get_display_devices.argtypes = [ctypes.POINTER(_DisplayDeviceInfo), ctypes.c_int]

_lib.get_edid.restype = ctypes.c_int
_lib.get_edid.argtypes = [ctypes.c_char_p, ctypes.POINTER(ctypes.c_ubyte), ctypes.c_int]


# ---- Python-facing dataclass ----

@dataclass
class DisplayDeviceInfo:
    device_id: str
    pnp_device_id: str
    monitor_name: str
    display_path: str
    gpu_name: str
    width: int
    height: int
    refresh_rate: int
    output_technology: int


# ---- public API ----

_MAX = 8


def _decode(raw: bytes) -> str:
    return raw.decode("utf-8", errors="replace").strip("\x00")


def get_display_devices() -> list[DisplayDeviceInfo]:
    """Enumerate active displays via user32 + CCD + DXGI in one pass."""
    buf = (_DisplayDeviceInfo * _MAX)()
    count = _lib.get_display_devices(buf, _MAX)
    if count < 0:
        raise RuntimeError("get_display_devices() failed (C library returned -1)")

    return [
        DisplayDeviceInfo(
            device_id=_decode(buf[i].device_id),
            pnp_device_id=_decode(buf[i].pnp_device_id),
            monitor_name=_decode(buf[i].monitor_name),
            display_path=_decode(buf[i].display_path),
            gpu_name=_decode(buf[i].gpu_name),
            width=buf[i].width,
            height=buf[i].height,
            refresh_rate=buf[i].refresh_rate,
            output_technology=buf[i].output_technology,
        )
        for i in range(count)
    ]


def get_edid(pnp_device_id: str) -> Optional[bytes]:
    """Read raw EDID bytes from the registry for a monitor matching the
    given PNP device ID or display path. Returns None if not found."""
    buf = (ctypes.c_ubyte * 1024)()
    count = _lib.get_edid(pnp_device_id.encode("utf-8"), buf, 1024)
    if count <= 0:
        return None
    return bytes(buf[:count])
