"""
storage_info.py  –  Python ctypes binding for storage enumeration via libdevice_info.dylib

Usage:
    from storage_info import get_storage_info
    disks = get_storage_info()
    for d in disks:
        print(d)

Source code is in `interops/mac/include/` and `interops/mac/src/`.
"""

import ctypes
import pathlib
from dataclasses import dataclass

_HERE = pathlib.Path(__file__).parent
_LIB_PATH = _HERE / "libdevice_info.dylib"

if not _LIB_PATH.exists():
    raise FileNotFoundError(
        f"libdevice_info.dylib not found at {_LIB_PATH}.\nBuild the project first:  cmake --build cmake-build-debug"
    )

_lib = ctypes.CDLL(str(_LIB_PATH))


class _StorageDeviceProperties(ctypes.Structure):
    _fields_ = [
        ("product_name", ctypes.c_char * 256),
        ("vendor_name", ctypes.c_char * 256),
        ("medium_type", ctypes.c_char * 128),
        ("interconnect", ctypes.c_char * 128),
        ("location", ctypes.c_char * 64),
        ("bsd_name", ctypes.c_char * 64),
        ("size_bytes", ctypes.c_uint64),
    ]


_lib.get_storage_info.restype = ctypes.c_int
_lib.get_storage_info.argtypes = [ctypes.POINTER(_StorageDeviceProperties), ctypes.c_int]


@dataclass
class StorageDeviceProperties:
    product_name: str
    vendor_name: str
    medium_type: str
    interconnect: str
    location: str
    bsd_name: str
    size_bytes: int

    def __str__(self) -> str:
        size_mb = self.size_bytes // (1024 * 1024) if self.size_bytes else 0
        lines = [
            f"  Product:      {self.product_name}",
            f"  Vendor:       {self.vendor_name}",
            f"  Medium Type:  {self.medium_type}",
            f"  Interconnect: {self.interconnect}",
            f"  Location:     {self.location}",
            f"  BSD Name:     {self.bsd_name}",
            f"  Size:         {size_mb} MB",
        ]
        return "\n".join(lines)


_MAX_DEVICES = 32


def get_storage_info() -> list[StorageDeviceProperties]:
    """Return a list of StorageDeviceProperties for every storage device found."""
    buf = (_StorageDeviceProperties * _MAX_DEVICES)()
    count = _lib.get_storage_info(buf, _MAX_DEVICES)
    if count < 0:
        raise RuntimeError("get_storage_info() failed (C library returned -1)")

    result = []
    for i in range(count):
        raw = buf[i]
        result.append(
            StorageDeviceProperties(
                product_name=raw.product_name.decode("utf-8", errors="replace").strip("\x00"),
                vendor_name=raw.vendor_name.decode("utf-8", errors="replace").strip("\x00"),
                medium_type=raw.medium_type.decode("utf-8", errors="replace").strip("\x00"),
                interconnect=raw.interconnect.decode("utf-8", errors="replace").strip("\x00"),
                location=raw.location.decode("utf-8", errors="replace").strip("\x00"),
                bsd_name=raw.bsd_name.decode("utf-8", errors="replace").strip("\x00"),
                size_bytes=raw.size_bytes,
            )
        )
    return result


if __name__ == "__main__":
    disks = get_storage_info()
    print(f"Found {len(disks)} storage device(s):\n")
    for idx, d in enumerate(disks):
        print(f"Disk {idx}:")
        print(d)
        print()
