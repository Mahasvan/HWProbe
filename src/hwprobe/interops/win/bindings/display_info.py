"""
display_info.py  -  Python ctypes binding for display_info.dll

Four exports covering all Win32 display APIs:
  - get_monitor_devices(): user32 monitor enumeration (EnumDisplayMonitors + settings)
  - get_display_connectors(): CCD API (QueryDisplayConfig) — connector type + display path
  - get_gpu_for_display(): DXGI output→adapter match — GPU name
  - get_edid(): SetupAPI + registry EDID lookup — raw EDID bytes

All Win32 calls live in C++ — Python only does EDID parsing and data assembly.

Usage:
    from hwprobe.interops.win.bindings.display_info import (
        get_monitor_devices, get_display_connectors, get_gpu_for_display, get_edid,
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


# ---- mirror the C structs ----

class _MonitorDevice(ctypes.Structure):
    _fields_ = [
        ("device_id", ctypes.c_char * 32),
        ("pnp_device_id", ctypes.c_char * 128),
        ("width", ctypes.c_int),
        ("height", ctypes.c_int),
        ("refresh_rate", ctypes.c_int),
    ]


class _ConnectorInfo(ctypes.Structure):
    _fields_ = [
        ("display_id", ctypes.c_char * 32),
        ("display_path", ctypes.c_char * 512),
        ("output_technology", ctypes.c_int),
    ]


# ---- function signatures ----

_lib.get_monitor_devices.restype = ctypes.c_int
_lib.get_monitor_devices.argtypes = [ctypes.POINTER(_MonitorDevice), ctypes.c_int]

_lib.get_display_connectors.restype = ctypes.c_int
_lib.get_display_connectors.argtypes = [ctypes.POINTER(_ConnectorInfo), ctypes.c_int]

_lib.get_gpu_for_display.restype = ctypes.c_int
_lib.get_gpu_for_display.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int]

_lib.get_edid.restype = ctypes.c_int
_lib.get_edid.argtypes = [ctypes.c_char_p, ctypes.POINTER(ctypes.c_ubyte), ctypes.c_int]


# ---- Python-facing dataclasses ----

@dataclass
class MonitorDevice:
    device_id: str
    pnp_device_id: str
    width: int
    height: int
    refresh_rate: int


@dataclass
class ConnectorInfo:
    display_id: str
    display_path: str
    output_technology: int


# ---- public API ----

_MAX = 8


def get_monitor_devices() -> list[MonitorDevice]:
    """Enumerate active monitors via user32. Returns one entry per attached display."""
    buf = (_MonitorDevice * _MAX)()
    count = _lib.get_monitor_devices(buf, _MAX)
    if count < 0:
        raise RuntimeError("get_monitor_devices() failed (C library returned -1)")

    return [
        MonitorDevice(
            device_id=buf[i].device_id.decode("utf-8", errors="replace").strip("\x00"),
            pnp_device_id=buf[i].pnp_device_id.decode("utf-8", errors="replace").strip("\x00"),
            width=buf[i].width,
            height=buf[i].height,
            refresh_rate=buf[i].refresh_rate,
        )
        for i in range(count)
    ]


def get_display_connectors() -> list[ConnectorInfo]:
    """Return active display connector info from the CCD API."""
    buf = (_ConnectorInfo * _MAX)()
    count = _lib.get_display_connectors(buf, _MAX)
    if count < 0:
        raise RuntimeError("get_display_connectors() failed (C library returned -1)")

    return [
        ConnectorInfo(
            display_id=buf[i].display_id.decode("utf-8", errors="replace").strip("\x00"),
            display_path=buf[i].display_path.decode("utf-8", errors="replace").strip("\x00"),
            output_technology=buf[i].output_technology,
        )
        for i in range(count)
    ]


def get_gpu_for_display(device_name: str) -> Optional[str]:
    """Find the GPU name driving a display device (e.g. r'\\.\DISPLAY1').
    Returns None if not found."""
    buf = ctypes.create_string_buffer(256)
    rc = _lib.get_gpu_for_display(device_name.encode("utf-8"), buf, 256)
    if rc != 0:
        return None
    name = buf.value.decode("utf-8", errors="replace").strip("\x00")
    return name or None


def get_edid(pnp_device_id: str) -> Optional[bytes]:
    """Read raw EDID bytes from the registry for a monitor matching the
    given PNP device ID or display path. Returns None if not found."""
    buf = (ctypes.c_ubyte * 1024)()
    count = _lib.get_edid(pnp_device_id.encode("utf-8"), buf, 1024)
    if count <= 0:
        return None
    return bytes(buf[:count])
