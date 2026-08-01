"""
Tests for hwprobe.core.windows.display

One C++ call (get_display_devices) does everything. Tests mock it + get_edid.
Uses direct-load pattern to bypass core.windows.__init__ which chains
into broken legacy imports.
"""

import importlib
import importlib.util
import pathlib
import struct
import sys
import types
from dataclasses import dataclass

import pytest

from hwprobe.models.display_models import DisplayInfo, DisplayModuleInfo, ResolutionInfo
from hwprobe.models.status_models import StatusType

_MODULE_PATH = pathlib.Path(__file__).resolve().parents[3] / "src" / "hwprobe" / "core" / "windows" / "display.py"


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


def _load_display_module():
    """Load display.py directly without triggering core.windows.__init__."""
    _binding = types.ModuleType("hwprobe.interops.win.bindings.display_info")
    _binding.DisplayDeviceInfo = DisplayDeviceInfo
    _binding.get_display_devices = lambda: []
    _binding.get_edid = lambda pnp: None
    sys.modules["hwprobe.interops.win.bindings.display_info"] = _binding

    _win_enum = types.ModuleType("hwprobe.core.windows.win_enum")
    _win_enum.DISPLAY_CON_TYPE = {4: "DVI", 5: "HDMI", 10: "DisplayPort", 11: "eDP"}
    sys.modules["hwprobe.core.windows.win_enum"] = _win_enum

    _common = types.ModuleType("hwprobe.core.windows.common")
    _common.format_acpi_path = lambda s: s
    _common.format_pci_path = lambda s: s
    sys.modules["hwprobe.core.windows.common"] = _common

    _loc = types.ModuleType("hwprobe.util.location_paths")
    _loc.get_location_paths = lambda pnp: None
    sys.modules["hwprobe.util.location_paths"] = _loc

    mod_name = "hwprobe.core.windows.display"
    if mod_name in sys.modules:
        return sys.modules[mod_name]
    spec = importlib.util.spec_from_file_location(mod_name, _MODULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


display = _load_display_module()


# ============================================================
# Helpers
# ============================================================


def _build_edid(name=b"TEST-MONITOR", width_cm=60, height_cm=34, year=2023):
    """Build a minimal 128-byte EDID matching the shared parser's expectations."""
    edid = bytearray(128)
    vendor = (1 << 10) | (2 << 5) | 3  # "ABC"

    edid[8:10] = struct.pack(">H", vendor)
    edid[10:12] = struct.pack("<H", 0x1234)
    edid[0x11] = year - 1990
    edid[0x12] = 1  # version 1.4
    edid[0x13] = 4
    edid[0x14] = 0x80  # digital input
    edid[21] = width_cm
    edid[22] = height_cm

    # Name descriptor at 0x36
    edid[0x36:0x3B] = b"\x00\x00\x00\xfc\x00"
    edid[0x3B:0x3B + len(name)] = name
    edid[0x3B + len(name)] = 0x0A
    for i in range(0x3B + len(name) + 1, 0x48):
        edid[i] = 0x20

    # Serial descriptor at 0x48
    serial = b"SN12345"
    edid[0x48:0x4D] = b"\x00\x00\x00\xff\x00"
    edid[0x4D:0x4D + len(serial)] = serial
    edid[0x4D + len(serial)] = 0x0A
    for i in range(0x4D + len(serial) + 1, 0x5A):
        edid[i] = 0x20

    return bytes(edid)


def _mock_dev(
    device_id=r"\\.\DISPLAY1",
    pnp_id=r"MONITOR\ABC123\{GUID}",
    monitor_name="",
    display_path=r"\\?\DISPLAY#ABC123",
    gpu_name="GPU-0",
    w=2560, h=1440, rr=144,
    tech=10,
):
    return DisplayDeviceInfo(
        device_id=device_id, pnp_device_id=pnp_id, monitor_name=monitor_name,
        display_path=display_path, gpu_name=gpu_name,
        width=w, height=h, refresh_rate=rr, output_technology=tech,
    )


# ============================================================
# EDID enrichment tests
# ============================================================


class TestEnrichFromEdid:
    def test_fills_name_year_serial_manufacturer(self):
        module = DisplayModuleInfo()
        display._enrich_from_edid(module, _build_edid())

        assert module.name == "TEST-MONITOR"
        assert module.year == 2023
        assert module.serial_number == "SN12345"
        assert module.manufacturer_code == "ABC"

    def test_fills_bit_depth_into_existing_resolution(self):
        module = DisplayModuleInfo()
        module.resolution = ResolutionInfo(width=2560, height=1440, refresh_rate=144.0)
        display._enrich_from_edid(module, _build_edid())

        assert module.resolution.width == 2560
        assert module.resolution.height == 1440
        assert module.resolution.refresh_rate == 144.0
        assert module.resolution.bit_depth is not None

    def test_fills_resolution_when_none(self):
        module = DisplayModuleInfo()
        display._enrich_from_edid(module, _build_edid())
        assert module.resolution is not None

    def test_does_not_overwrite_existing_fields(self):
        module = DisplayModuleInfo(name="Custom Name", year=2020)
        display._enrich_from_edid(module, _build_edid())

        assert module.name == "Custom Name"
        assert module.year == 2020
        assert module.serial_number == "SN12345"


# ============================================================
# fetch_display_info tests
# ============================================================


class TestFetchDisplayInfo:
    def test_no_displays_returns_failed(self, monkeypatch):
        monkeypatch.setattr(display, "get_display_devices", lambda: [])
        result = display.fetch_display_info()
        assert result.status.type == StatusType.FAILED

    def test_happy_path(self, monkeypatch):
        monkeypatch.setattr(display, "get_display_devices", lambda: [_mock_dev()])
        monkeypatch.setattr(display, "get_edid", lambda key: _build_edid())
        monkeypatch.setattr(display, "get_location_paths", lambda pnp: ("PCIROOT(0)#PCI(1D00)", "ACPI(_SB_)#ACPI(PCI0)#ACPI(NIC0)"))

        result = display.fetch_display_info()

        assert len(result.modules) == 1
        mod = result.modules[0]
        assert mod.name == "TEST-MONITOR"
        assert mod.gpu_name == "GPU-0"
        assert mod.interface == "DisplayPort"
        assert mod.acpi_path is not None
        assert mod.pci_path is not None
        assert mod.resolution.width == 2560
        assert mod.resolution.height == 1440
        assert mod.resolution.refresh_rate == 144.0
        assert mod.serial_number == "SN12345"
        assert mod.manufacturer_code == "ABC"
        assert mod.year == 2023

    def test_no_edid_still_returns_module(self, monkeypatch):
        monkeypatch.setattr(display, "get_display_devices", lambda: [
            _mock_dev(pnp_id=r"MONITOR\XYZ\{GUID}", w=1920, h=1080, rr=60, gpu_name=""),
        ])
        monkeypatch.setattr(display, "get_edid", lambda key: None)
        monkeypatch.setattr(display, "get_location_paths", lambda pnp: None)

        result = display.fetch_display_info()

        assert len(result.modules) == 1
        mod = result.modules[0]
        assert mod.name is None
        assert mod.gpu_name is None
        assert mod.resolution.width == 1920
        assert mod.acpi_path is None

    def test_multiple_displays(self, monkeypatch):
        monkeypatch.setattr(display, "get_display_devices", lambda: [
            _mock_dev(device_id=r"\\.\DISPLAY1", pnp_id=r"MONITOR\AAA\{1}", w=2560, h=1440, rr=144),
            _mock_dev(device_id=r"\\.\DISPLAY2", pnp_id=r"MONITOR\BBB\{2}", w=1920, h=1080, rr=60),
        ])
        monkeypatch.setattr(display, "get_edid", lambda key: None)
        monkeypatch.setattr(display, "get_location_paths", lambda pnp: None)

        result = display.fetch_display_info()

        assert len(result.modules) == 2
        assert result.modules[0].resolution.width == 2560
        assert result.modules[1].resolution.width == 1920

    def test_ccd_name_fallback(self, monkeypatch):
        """When EDID doesn't have a name descriptor, use CCD monitorFriendlyName."""
        monkeypatch.setattr(display, "get_display_devices", lambda: [
            _mock_dev(monitor_name="BOE LCD Panel"),
        ])
        monkeypatch.setattr(display, "get_edid", lambda key: None)
        monkeypatch.setattr(display, "get_location_paths", lambda pnp: None)

        result = display.fetch_display_info()
        assert result.modules[0].name == "BOE LCD Panel"

    def test_edid_name_wins_over_ccd(self, monkeypatch):
        """EDID name takes priority over CCD monitorFriendlyName."""
        monkeypatch.setattr(display, "get_display_devices", lambda: [
            _mock_dev(monitor_name="Generic PnP Monitor"),
        ])
        monkeypatch.setattr(display, "get_edid", lambda key: _build_edid())
        monkeypatch.setattr(display, "get_location_paths", lambda pnp: None)

        result = display.fetch_display_info()
        assert result.modules[0].name == "TEST-MONITOR"
