"""
Tests for hwprobe.core.windows.graphics

Strategy: patch the binding import so we never load the real device_info.dll.
We build fake GPUProperties dataclass instances that mirror the real binding.

The module under test (hwprobe.core.windows.graphics) only depends on the
binding module, but importing it via the package triggers __init__.py which
chains into Win32-only ctypes structs. We use importlib to load the module
directly, bypassing the package __init__.
"""

import importlib
import importlib.util
import pathlib
import sys
from dataclasses import dataclass
from typing import Optional
from unittest.mock import MagicMock, patch

from hwprobe.models.status_models import StatusType

_MODULE_PATH = pathlib.Path(__file__).resolve().parents[3] / "src" / "hwprobe" / "core" / "windows" / "graphics.py"


def _load_graphics_module():
    """Load graphics.py directly without triggering the package __init__."""
    mod_name = "hwprobe.core.windows.graphics"
    if mod_name in sys.modules:
        return sys.modules[mod_name]
    spec = importlib.util.spec_from_file_location(mod_name, _MODULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


@dataclass
class FakeGPUProperties:
    name: str
    manufacturer: str
    vendor_id: int
    device_id: int
    subsystem_vendor_id: int
    subsystem_device_id: int
    acpi_path: Optional[str] = None
    pci_path: Optional[str] = None
    vram_mb: int = 0
    pcie_gen: int = 0
    pcie_width: int = 0


def _gpu(
    name="NVIDIA GeForce RTX 4090",
    manufacturer="NVIDIA",
    vendor_id=0x10DE,
    device_id=0x2684,
    subsystem_vendor_id=0x1043,
    subsystem_device_id=0x8888,
    acpi_path=r"\_SB.PCI0.PEG0.PEGP",
    pci_path="PciRoot(0x0)/Pci(0x1,0x0)/Pci(0x0,0x0)",
    vram_mb=24576,
    pcie_gen=4,
    pcie_width=16,
) -> FakeGPUProperties:
    return FakeGPUProperties(
        name=name,
        manufacturer=manufacturer,
        vendor_id=vendor_id,
        device_id=device_id,
        subsystem_vendor_id=subsystem_vendor_id,
        subsystem_device_id=subsystem_device_id,
        acpi_path=acpi_path,
        pci_path=pci_path,
        vram_mb=vram_mb,
        pcie_gen=pcie_gen,
        pcie_width=pcie_width,
    )


def _patch_binding(gpu_list):
    mock_module = MagicMock()
    mock_module.get_gpu_info.return_value = gpu_list
    mock_module.GPUProperties = FakeGPUProperties
    return patch.dict(
        "sys.modules",
        {"hwprobe.interops.win.bindings.gpu_info": mock_module},
    )


def _run(gpu_list):
    sys.modules.pop("hwprobe.interops.win.bindings.gpu_info", None)
    sys.modules.pop("hwprobe.core.windows.graphics", None)
    with _patch_binding(gpu_list):
        mod = _load_graphics_module()
        return mod.fetch_graphics_info()


class TestHappyPath:
    def test_single_gpu_success(self):
        info = _run([_gpu()])

        assert info.status.type == StatusType.SUCCESS
        assert len(info.modules) == 1

        gpu = info.modules[0]
        assert gpu.name == "NVIDIA GeForce RTX 4090"
        assert gpu.manufacturer == "NVIDIA"
        assert gpu.vendor_id == "0x10DE"
        assert gpu.device_id == "0x2684"
        assert gpu.subsystem_manufacturer == "0x1043"
        assert gpu.subsystem_model == "0x8888"

    def test_vram_populated(self):
        info = _run([_gpu(vram_mb=24576)])
        gpu = info.modules[0]
        assert gpu.vram is not None
        assert gpu.vram.capacity == 24576

    def test_pcie_fields_populated(self):
        info = _run([_gpu(pcie_gen=4, pcie_width=16)])
        gpu = info.modules[0]
        assert gpu.pcie_gen == 4
        assert gpu.pcie_width == 16

    def test_acpi_and_pci_paths_populated(self):
        info = _run(
            [
                _gpu(
                    acpi_path=r"\_SB.PCI0.PEG0.PEGP",
                    pci_path="PciRoot(0x0)/Pci(0x1,0x0)/Pci(0x0,0x0)",
                )
            ]
        )
        gpu = info.modules[0]
        assert gpu.acpi_path == r"\_SB.PCI0.PEG0.PEGP"
        assert gpu.pci_path == "PciRoot(0x0)/Pci(0x1,0x0)/Pci(0x0,0x0)"

    def test_return_type_is_graphics_info(self):
        from hwprobe.models.gpu_models import GraphicsInfo

        info = _run([_gpu()])
        assert isinstance(info, GraphicsInfo)


class TestMultipleGPUs:
    def test_igpu_plus_dgpu(self):
        igpu = _gpu(
            name="Intel UHD Graphics 630",
            manufacturer="Intel",
            vendor_id=0x8086,
            device_id=0x3E92,
            vram_mb=0,
            pcie_gen=0,
            pcie_width=0,
        )
        dgpu = _gpu(
            name="NVIDIA GeForce RTX 3080",
            manufacturer="NVIDIA",
            vendor_id=0x10DE,
            device_id=0x2206,
            vram_mb=10240,
            pcie_gen=4,
            pcie_width=16,
        )
        info = _run([igpu, dgpu])

        assert len(info.modules) == 2
        assert info.modules[0].name == "Intel UHD Graphics 630"
        assert info.modules[1].name == "NVIDIA GeForce RTX 3080"

    def test_dual_amd_gpus(self):
        gpu1 = _gpu(name="AMD Radeon RX 7900 XTX", manufacturer="AMD", vendor_id=0x1002, device_id=0x744C)
        gpu2 = _gpu(name="AMD Radeon RX 7900 XT", manufacturer="AMD", vendor_id=0x1002, device_id=0x744C)
        info = _run([gpu1, gpu2])

        assert len(info.modules) == 2


class TestZeroAndMissingFields:
    def test_zero_vram_results_in_none(self):
        info = _run([_gpu(vram_mb=0)])
        assert info.modules[0].vram is None

    def test_zero_pcie_gen_results_in_none(self):
        info = _run([_gpu(pcie_gen=0)])
        assert info.modules[0].pcie_gen is None

    def test_zero_pcie_width_results_in_none(self):
        info = _run([_gpu(pcie_width=0)])
        assert info.modules[0].pcie_width is None

    def test_none_acpi_path_preserved(self):
        info = _run([_gpu(acpi_path=None)])
        assert info.modules[0].acpi_path is None

    def test_none_pci_path_preserved(self):
        info = _run([_gpu(pci_path=None)])
        assert info.modules[0].pci_path is None


class TestFailurePaths:
    def test_runtime_error_returns_failed(self):
        mock_module = MagicMock()
        mock_module.get_gpu_info.side_effect = RuntimeError("get_gpu_info() failed (C library returned -1)")

        sys.modules.pop("hwprobe.interops.win.bindings.gpu_info", None)
        sys.modules.pop("hwprobe.core.windows.graphics", None)

        with patch.dict("sys.modules", {"hwprobe.interops.win.bindings.gpu_info": mock_module}):
            mod = _load_graphics_module()
            info = mod.fetch_graphics_info()

        assert info.status.type == StatusType.FAILED
        assert any("-1" in m for m in info.status.messages)
        assert info.modules == []

    def test_empty_gpu_list_returns_failed(self):
        info = _run([])

        assert info.status.type == StatusType.FAILED
        assert any("No GPUs" in m for m in info.status.messages)
        assert info.modules == []


class TestVendorIdFormatting:
    def test_vendor_id_hex_format(self):
        info = _run([_gpu(vendor_id=0x10DE)])
        assert info.modules[0].vendor_id == "0x10DE"

    def test_device_id_hex_format(self):
        info = _run([_gpu(device_id=0x2684)])
        assert info.modules[0].device_id == "0x2684"

    def test_subsystem_ids_hex_format(self):
        info = _run([_gpu(subsystem_vendor_id=0x1043, subsystem_device_id=0x8888)])
        gpu = info.modules[0]
        assert gpu.subsystem_manufacturer == "0x1043"
        assert gpu.subsystem_model == "0x8888"
