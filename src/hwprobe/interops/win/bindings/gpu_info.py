"""
gpu_info.py  -  Python ctypes binding for gpu_info.dll (GPU info)

Usage:
    from hwprobe.interops.win.bindings.gpu_info import get_gpu_info
    gpus = get_gpu_info()
    for g in gpus:
        print(g)

Source code is in `interops/win/include/` and `interops/win/src/`.
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


# ---- Mirror the C structs ----


class _WinGPUProperties(ctypes.Structure):
    _fields_ = [
        ("name", ctypes.c_char * 256),
        ("manufacturer", ctypes.c_char * 256),
        ("vendor_id", ctypes.c_uint32),
        ("device_id", ctypes.c_uint32),
        ("subsystem_vendor_id", ctypes.c_uint32),
        ("subsystem_device_id", ctypes.c_uint32),
        ("acpi_path", ctypes.c_char * 512),
        ("pci_path", ctypes.c_char * 512),
        ("vram_mb", ctypes.c_uint64),
        ("pcie_gen", ctypes.c_int),
        ("pcie_width", ctypes.c_int),
    ]


_lib.get_gpu_info.restype = ctypes.c_int
_lib.get_gpu_info.argtypes = [ctypes.POINTER(_WinGPUProperties), ctypes.c_int]


# ---- Python-facing dataclass ----


@dataclass
class GPUProperties:
    name: str
    manufacturer: str
    vendor_id: int
    device_id: int
    subsystem_vendor_id: int
    subsystem_device_id: int
    acpi_path: Optional[str]
    pci_path: Optional[str]
    vram_mb: int
    pcie_gen: int
    pcie_width: int

    def __str__(self) -> str:
        lines = [
            f"  Name:             {self.name}",
            f"  Manufacturer:     {self.manufacturer}",
            f"  Vendor ID:        0x{self.vendor_id:04X}",
            f"  Device ID:        0x{self.device_id:04X}",
            f"  Subsystem Vendor: 0x{self.subsystem_vendor_id:04X}",
            f"  Subsystem Device: 0x{self.subsystem_device_id:04X}",
            f"  VRAM:             {self.vram_mb} MB",
        ]
        if self.pcie_gen:
            lines.append(f"  PCIe Gen:         {self.pcie_gen}")
        if self.pcie_width:
            lines.append(f"  PCIe Width:       x{self.pcie_width}")
        if self.acpi_path:
            lines.append(f"  ACPI Path:        {self.acpi_path}")
        if self.pci_path:
            lines.append(f"  PCI Path:         {self.pci_path}")
        return "\n".join(lines)


# ---- Public API ----

_MAX_GPUS = 8


def get_gpu_info() -> list[GPUProperties]:
    """Return a list of GPUProperties for every GPU found on this machine."""
    buf = (_WinGPUProperties * _MAX_GPUS)()
    count = _lib.get_gpu_info(buf, _MAX_GPUS)
    if count < 0:
        raise RuntimeError("get_gpu_info() failed (C library returned -1)")

    result = []
    for i in range(count):
        raw = buf[i]
        acpi = raw.acpi_path.decode("utf-8", errors="replace").strip("\x00") or None
        pci = raw.pci_path.decode("utf-8", errors="replace").strip("\x00") or None

        result.append(
            GPUProperties(
                name=raw.name.decode("utf-8", errors="replace").strip("\x00"),
                manufacturer=raw.manufacturer.decode("utf-8", errors="replace").strip("\x00"),
                vendor_id=raw.vendor_id,
                device_id=raw.device_id,
                subsystem_vendor_id=raw.subsystem_vendor_id,
                subsystem_device_id=raw.subsystem_device_id,
                acpi_path=acpi,
                pci_path=pci,
                vram_mb=raw.vram_mb,
                pcie_gen=raw.pcie_gen,
                pcie_width=raw.pcie_width,
            )
        )
    return result


if __name__ == "__main__":
    gpus = get_gpu_info()
    print(f"Found {len(gpus)} GPU(s):\n")
    for idx, g in enumerate(gpus):
        print(f"GPU {idx}:")
        print(g)
        print()
