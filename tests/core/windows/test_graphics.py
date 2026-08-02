"""
Tests for hwprobe.core.windows.graphics

Strategy: patch the binding + util modules so we never load the real DLLs.
We build fake GPURaw dataclass instances that mirror the real binding, and
mock util.location_paths + core.windows.common for location/PCIe formatting.

The module under test (hwprobe.core.windows.graphics) depends on the binding
module and util.location_paths, both of which touch Win32-only DLLs. We patch
both via sys.modules and load graphics.py directly via importlib, bypassing
the package __init__.
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
_COMMON_PATH = pathlib.Path(__file__).resolve().parents[3] / "src" / "hwprobe" / "core" / "windows" / "common.py"


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


def _load_common_module():
    """Load common.py directly (format_acpi_path / format_pci_path) without
    triggering core.windows.__init__ which chains into legacy imports."""
    mod_name = "hwprobe.core.windows.common"
    if mod_name in sys.modules:
        return sys.modules[mod_name]
    spec = importlib.util.spec_from_file_location(mod_name, _COMMON_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


# ---- Fake binding: GPURaw with raw fields only ----

@dataclass
class FakeGPURaw:
    name: str
    vendor_id: int
    device_id: int
    subsystem_id: int
    dedicated_video_memory_bytes: int
    pnp_device_id: Optional[str] = None
    vram_bytes: int = 0


def _gpu(
    name="NVIDIA GeForce RTX 4090",
    vendor_id=0x10DE,
    device_id=0x2684,
    # subsystem_id encodes vendor (high 16) + device (low 16)
    # 0x10438888 -> subsystem_vendor=0x1043, subsystem_device=0x8888
    subsystem_id=0x10438888,
    dedicated_video_memory_bytes=24576 * 1024 * 1024,
    pnp_device_id=r"PCI\VEN_10DE&DEV_2684&SUBSYS_10438888&REV_A1",
    vram_bytes=0,
) -> FakeGPURaw:
    return FakeGPURaw(
        name=name,
        vendor_id=vendor_id,
        device_id=device_id,
        subsystem_id=subsystem_id,
        dedicated_video_memory_bytes=dedicated_video_memory_bytes,
        pnp_device_id=pnp_device_id,
        vram_bytes=vram_bytes,
    )


# ---- Mock helpers for location_paths + common ----

_DEFAULT_PATHS = [
    r"ACPI(_SB_)#ACPI(PCI0)#ACPI(PEG0)#ACPI(PEGP)",
    r"PCIROOT(0)#PCI(1C05)#PCI(0000)",
]
_DEFAULT_PCIE = (4, 16)
# Sentinel so callers can pass pcie=None explicitly (distinct from "use default").
_UNSET = object()


def _patch_modules(gpu_list, paths=None, pcie=_UNSET):
    """Patch gpu_info binding + util.location_paths + core.windows.common."""
    if paths is None:
        paths = _DEFAULT_PATHS
    if pcie is _UNSET:
        pcie = _DEFAULT_PCIE

    gpu_mock = MagicMock()
    gpu_mock.get_gpu_info.return_value = gpu_list
    gpu_mock.GPURaw = FakeGPURaw

    loc_mock = MagicMock()
    loc_mock.get_location_paths.return_value = paths
    loc_mock.fetch_pcie_info.return_value = pcie

    common_mock = MagicMock()
    # Use the real format functions so path formatting is exercised.
    common_mod = _load_common_module()
    common_mock.format_acpi_path.side_effect = common_mod.format_acpi_path
    common_mock.format_pci_path.side_effect = common_mod.format_pci_path

    return patch.dict(
        "sys.modules",
        {
            "hwprobe.interops.win.bindings.gpu_info": gpu_mock,
            "hwprobe.util.location_paths": loc_mock,
            "hwprobe.core.windows.common": common_mock,
        },
    )


def _run(gpu_list, paths=None, pcie=None):
    for m in ("hwprobe.interops.win.bindings.gpu_info",
              "hwprobe.util.location_paths",
              "hwprobe.core.windows.common",
              "hwprobe.core.windows.graphics"):
        sys.modules.pop(m, None)
    with _patch_modules(gpu_list, paths, pcie):
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

    def test_vram_populated_from_dxgi(self):
        info = _run([_gpu(dedicated_video_memory_bytes=24576 * 1024 * 1024)])
        gpu = info.modules[0]
        assert gpu.vram is not None
        assert gpu.vram.capacity == 24576

    def test_vram_registry_fallback_wins(self):
        info = _run([_gpu(
            dedicated_video_memory_bytes=4096 * 1024 * 1024,
            vram_bytes=24576 * 1024 * 1024,
        )])
        gpu = info.modules[0]
        assert gpu.vram is not None
        assert gpu.vram.capacity == 24576

    def test_pcie_fields_populated(self):
        info = _run([_gpu()], pcie=(4, 16))
        gpu = info.modules[0]
        assert gpu.pcie_gen == 4
        assert gpu.pcie_width == 16

    def test_acpi_and_pci_paths_populated(self):
        info = _run([_gpu()])
        gpu = info.modules[0]
        assert gpu.acpi_path == r"\_SB_.PCI0.PEG0.PEGP"
        assert gpu.pci_path == "PciRoot(0x0)/Pci(0x1C,0x5)/Pci(0x0,0x0)"

    def test_return_type_is_graphics_info(self):
        from hwprobe.models.gpu_models import GraphicsInfo

        info = _run([_gpu()])
        assert isinstance(info, GraphicsInfo)


class TestMultipleGPUs:
    def test_igpu_plus_dgpu(self):
        igpu = _gpu(
            name="Intel UHD Graphics 630",
            vendor_id=0x8086,
            device_id=0x3E92,
            dedicated_video_memory_bytes=0,
        )
        dgpu = _gpu(
            name="NVIDIA GeForce RTX 3080",
            vendor_id=0x10DE,
            device_id=0x2206,
            dedicated_video_memory_bytes=10240 * 1024 * 1024,
        )
        info = _run([igpu, dgpu])

        assert len(info.modules) == 2
        assert info.modules[0].name == "Intel UHD Graphics 630"
        assert info.modules[1].name == "NVIDIA GeForce RTX 3080"

    def test_dual_amd_gpus(self):
        gpu1 = _gpu(name="AMD Radeon RX 7900 XTX", vendor_id=0x1002, device_id=0x744C)
        gpu2 = _gpu(name="AMD Radeon RX 7900 XT", vendor_id=0x1002, device_id=0x744C)
        info = _run([gpu1, gpu2])

        assert len(info.modules) == 2


class TestZeroAndMissingFields:
    def test_zero_vram_results_in_none(self):
        info = _run([_gpu(dedicated_video_memory_bytes=0, vram_bytes=0)])
        assert info.modules[0].vram is None

    def test_none_pcie_returns_none(self):
        info = _run([_gpu()], pcie=None)
        assert info.modules[0].pcie_gen is None
        assert info.modules[0].pcie_width is None

    def test_no_pnp_device_id_skips_location_lookup(self):
        info = _run([_gpu(pnp_device_id=None)])
        gpu = info.modules[0]
        assert gpu.acpi_path is None
        assert gpu.pci_path is None

    def test_empty_location_paths(self):
        info = _run([_gpu()], paths=[])
        gpu = info.modules[0]
        assert gpu.acpi_path is None
        assert gpu.pci_path is None


class TestFailurePaths:
    def test_runtime_error_returns_failed(self):
        gpu_mock = MagicMock()
        gpu_mock.get_gpu_info.side_effect = RuntimeError("get_gpu_info() failed (C library returned -1)")

        loc_mock = MagicMock()
        common_mock = MagicMock()

        for m in ("hwprobe.interops.win.bindings.gpu_info",
                  "hwprobe.util.location_paths",
                  "hwprobe.core.windows.common",
                  "hwprobe.core.windows.graphics"):
            sys.modules.pop(m, None)

        with patch.dict("sys.modules", {
            "hwprobe.interops.win.bindings.gpu_info": gpu_mock,
            "hwprobe.util.location_paths": loc_mock,
            "hwprobe.core.windows.common": common_mock,
        }):
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
        info = _run([_gpu(subsystem_id=0x10438888)])
        gpu = info.modules[0]
        assert gpu.subsystem_manufacturer == "0x1043"
        assert gpu.subsystem_model == "0x8888"

    def test_unknown_vendor_uses_hex(self):
        info = _run([_gpu(vendor_id=0x1234)])
        assert "0x1234" in info.modules[0].manufacturer
