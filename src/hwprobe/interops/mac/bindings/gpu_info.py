"""
gpu_info.py  –  Python ctypes binding for libdevice_info.dylib

Usage:
    from gpu_info import get_gpu_info
    gpus = get_gpu_info()
    for g in gpus:
        print(g)

Source code is in `interops/mac/include/` and `interops/mac/src/`.
"""

import ctypes
import pathlib
from dataclasses import dataclass
from typing import Optional

# ── locate the dylib ────────────────────────────────────────────────────────
_HERE = pathlib.Path(__file__).parent
_LIB_PATH = _HERE / "libdevice_info.dylib"

if not _LIB_PATH.exists():
    raise FileNotFoundError(
        f"libdevice_info.dylib not found at {_LIB_PATH}.\nBuild the project first:  cmake --build cmake-build-debug"
    )

_lib = ctypes.CDLL(str(_LIB_PATH))


# ── mirror the C structs ─────────────────────────────────────────────────────


class _AppleGPUProperties(ctypes.Structure):
    _fields_ = [
        ("core_count", ctypes.c_int),
        ("gpu_perf_shaders", ctypes.c_int),
        ("gpu_gen", ctypes.c_int),
        ("unified_memory_mb", ctypes.c_uint64),
    ]


class _GPUProperties(ctypes.Structure):
    _fields_ = [
        ("name", ctypes.c_char * 256),
        ("vendor_id", ctypes.c_uint32),
        ("device_id", ctypes.c_uint32),
        ("acpi_path", ctypes.c_char * 512),
        ("pci_path", ctypes.c_char * 512),
        ("vram_mb", ctypes.c_uint64),
        ("capable_pcie_gen", ctypes.c_uint32),
        ("capable_pcie_width", ctypes.c_uint32),
        ("negotiated_pcie_gen", ctypes.c_uint32),
        ("negotiated_pcie_width", ctypes.c_uint32),
        ("is_apple_silicon", ctypes.c_int),
        ("apple_gpu", _AppleGPUProperties),
    ]


# ── function signature ───────────────────────────────────────────────────────
_lib.get_gpu_info.restype = ctypes.c_int
_lib.get_gpu_info.argtypes = [ctypes.POINTER(_GPUProperties), ctypes.c_int]


# ── Python-facing dataclasses ────────────────────────────────────────────────


@dataclass
class AppleGPUProperties:
    core_count: int
    gpu_perf_shaders: int  # num_gps: GPU performance shader count
    gpu_gen: int
    unified_memory_mb: int  # Total system (unified) memory in MB

    def __str__(self) -> str:
        lines = [
            f"    GPU Cores:     {self.core_count}",
            f"    Perf Shaders:  {self.gpu_perf_shaders}",
            f"    GPU Gen:       {self.gpu_gen}",
            f"    Unified Mem:   {self.unified_memory_mb} MB",
        ]
        return "\n".join(lines)


@dataclass
class GPUProperties:
    name: str
    vendor_id: int
    device_id: int
    acpi_path: Optional[str]
    pci_path: Optional[str]
    vram_mb: int
    capable_pcie_gen: int
    capable_pcie_width: int
    negotiated_pcie_gen: int
    negotiated_pcie_width: int
    is_apple_silicon: bool
    apple_gpu: Optional[AppleGPUProperties]  # None for non-Apple GPUs

    def __str__(self) -> str:
        lines = [
            f"  Name:         {self.name}",
            f"  Vendor ID:    0x{self.vendor_id:04X}",
            f"  Device ID:    0x{self.device_id:04X}",
        ]
        if self.is_apple_silicon and self.apple_gpu:
            lines.append("  Apple Silicon GPU:")
            lines.append(str(self.apple_gpu))
        if self.acpi_path:
            lines.append(f"  ACPI Path:    {self.acpi_path}")
        if self.pci_path:
            lines.append(f"  PCI Path:     {self.pci_path}")
        if self.vram_mb:
            lines.append(f"  VRAM:         {self.vram_mb} MB")
        return "\n".join(lines)


# ── public API ───────────────────────────────────────────────────────────────

_MAX_GPUS = 16


def get_gpu_info() -> list[GPUProperties]:
    """Return a list of GPUProperties for every GPU found on this machine."""
    buf = (_GPUProperties * _MAX_GPUS)()
    count = _lib.get_gpu_info(buf, _MAX_GPUS)
    if count < 0:
        raise RuntimeError("get_gpu_info() failed (C library returned -1)")

    result: list[GPUProperties] = []
    for i in range(count):
        raw = buf[i]
        apple = None
        if raw.is_apple_silicon:
            apple = AppleGPUProperties(
                core_count=raw.apple_gpu.core_count,
                gpu_perf_shaders=raw.apple_gpu.gpu_perf_shaders,
                gpu_gen=raw.apple_gpu.gpu_gen,
                unified_memory_mb=raw.apple_gpu.unified_memory_mb,
            )
        acpi = raw.acpi_path.decode("utf-8", errors="replace").strip("\x00") or None
        pci = raw.pci_path.decode("utf-8", errors="replace").strip("\x00") or None

        result.append(
            GPUProperties(
                name=raw.name.decode("utf-8", errors="replace"),
                vendor_id=raw.vendor_id,
                device_id=raw.device_id,
                acpi_path=acpi,
                pci_path=pci,
                vram_mb=raw.vram_mb,
                capable_pcie_gen=raw.capable_pcie_gen,
                capable_pcie_width=raw.capable_pcie_width,
                negotiated_pcie_gen=raw.negotiated_pcie_gen,
                negotiated_pcie_width=raw.negotiated_pcie_width,
                is_apple_silicon=bool(raw.is_apple_silicon),
                apple_gpu=apple,
            )
        )
    return result


# ── quick self-test ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    gpus = get_gpu_info()
    print(f"Found {len(gpus)} GPU(s):\n")
    for idx, g in enumerate(gpus):
        print(f"GPU {idx}:")
        print(g)
        print()
