import builtins
import os
import posixpath
from unittest.mock import mock_open

import pytest

from hwprobe.core.linux.display import (
    _extract_pci_bdf_from_sysfs_path,
    _fetch_individual_monitor_info,
    _parse_connector_type,
    fetch_display_info,
)
from hwprobe.models.display_models import DisplayModuleInfo
from hwprobe.models.status_models import StatusType


class TestExtractPciBdfFromSysfsPath:
    def test_returns_last_bdf_in_chain(self):
        path = "/sys/devices/pci0000:00/0000:00:02.0/0000:05:00.0/drm/card0"
        assert _extract_pci_bdf_from_sysfs_path(path) == "0000:05:00.0"

    def test_single_bdf(self):
        path = "/sys/devices/pci0000:00/0000:00:02.0/drm/card0"
        assert _extract_pci_bdf_from_sysfs_path(path) == "0000:00:02.0"

    def test_no_pci_device(self):
        path = "/sys/devices/platform/simple-framebuffer/drm/card0"
        assert _extract_pci_bdf_from_sysfs_path(path) is None

    def test_empty_path(self):
        assert _extract_pci_bdf_from_sysfs_path("") is None


class TestFetchIndividualMonitorInfo:
    DEVICE_PATH = "/sys/class/drm/card0/card0-eDP-1"
    EDID_PATH = posixpath.join(DEVICE_PATH, "edid")
    ACPI_PATH = posixpath.join(DEVICE_PATH, "firmware_node", "path")

    def _patch_exists(self, monkeypatch, paths):
        monkeypatch.setattr(posixpath, "exists", lambda p: p in paths)

    def test_returns_none_when_edid_missing(self, monkeypatch):
        self._patch_exists(monkeypatch, set())
        assert _fetch_individual_monitor_info(self.DEVICE_PATH, []) is None

    def test_returns_none_when_edid_empty(self, monkeypatch):
        self._patch_exists(monkeypatch, {self.EDID_PATH})
        monkeypatch.setattr(
            builtins,
            "open",
            lambda *a, **kw: mock_open(read_data=b"")(),
        )
        assert _fetch_individual_monitor_info(self.DEVICE_PATH, []) is None

    def test_acpi_path_populated_when_firmware_node_exists(self, monkeypatch):
        self._patch_exists(monkeypatch, {self.EDID_PATH, self.ACPI_PATH})

        real_open = builtins.open

        def fake_open(path, *args, **kwargs):
            if path == self.EDID_PATH:
                return mock_open(read_data=b"\x01\x02")()
            if path == self.ACPI_PATH:
                return mock_open(read_data=r"\_SB.PCI0.GFX0.DD1F")()
            return real_open(path, *args, **kwargs)

        monkeypatch.setattr(builtins, "open", fake_open)
        monkeypatch.setattr(
            "hwprobe.core.linux.display.parse_edid",
            lambda _: DisplayModuleInfo(name="Display"),
        )
        monkeypatch.setattr(
            posixpath,
            "realpath",
            lambda _: "/sys/devices/pci0000:00/0000:00:02.0/drm/card0",
        )
        monkeypatch.setattr(
            "hwprobe.core.linux.display.pci_path_linux",
            lambda slot: "PciRoot(0x0)/Pci(0x2,0x0)",
        )

        monitor = _fetch_individual_monitor_info(self.DEVICE_PATH, [])

        assert monitor is not None
        assert monitor.acpi_path == r"\_SB.PCI0.GFX0.DD1F"


class TestFetchDisplayInfo:
    def test_collects_monitors_from_drm(self, monkeypatch):
        monkeypatch.setattr(posixpath, "isdir", lambda p: p == "/sys/class/drm")

        info = fetch_display_info([])

        assert len(info.modules) == 2

    def test_skips_monitors_returning_none(self, monkeypatch):
        monkeypatch.setattr(posixpath, "isdir", lambda p: p == "/sys/class/drm")
        monkeypatch.setattr(
            os,
            "listdir",
            lambda path: {
                "/sys/class/drm": ["card0"],
                "/sys/class/drm/card0": ["card0-eDP-1"],
            }.get(path, []),
        )
        monkeypatch.setattr(
            "hwprobe.core.linux.display._fetch_individual_monitor_info",
            lambda path: None,
        )

        info = fetch_display_info([])

        assert len(info.modules) == 0

    def test_failed_when_drm_root_missing(self, monkeypatch):
        monkeypatch.setattr(posixpath, "isdir", lambda p: False)

        info = fetch_display_info([])

        assert info.status.type == StatusType.FAILED
        assert any("/sys/class/drm" in m for m in info.status.messages)
        assert info.modules == []

    def test_partial_when_monitor_raises(self, monkeypatch):
        monkeypatch.setattr(posixpath, "isdir", lambda p: p == "/sys/class/drm")
        monkeypatch.setattr(
            os,
            "listdir",
            lambda path: {
                "/sys/class/drm": ["card0", "card1"],
                "/sys/class/drm/card0": ["card0-DP-1"],
                "/sys/class/drm/card1": ["card1-HDMI-A-1"],
            }.get(path, []),
        )

        def _mock_fetch(path, gpu_devices):
            if path.endswith("card0-DP-1"):
                raise RuntimeError("EDID decode failed")
            return DisplayModuleInfo(name="Monitor B")

        monkeypatch.setattr(
            "hwprobe.core.linux.display._fetch_individual_monitor_info",
            _mock_fetch,
        )

        info = fetch_display_info([])

        assert info.status.type == StatusType.PARTIAL
        assert any("card0-DP-1" in m for m in info.status.messages)
        assert len(info.modules) == 1
        assert info.modules[0].name == "Monitor B"


class TestParseConnectorType:
    @pytest.mark.parametrize(
        "dirname,expected",
        [
            ("card0-eDP-1", "DisplayPort"),
            ("card0-DP-1", "DisplayPort"),
            ("card0-DP-2", "DisplayPort"),
            ("card1-HDMI-A-1", "HDMI"),
            ("card0-HDMI-B-1", "HDMI (B)"),
            ("card0-DVI-D-1", "DVI"),
            ("card0-DVI-I-1", "DVI"),
            ("card0-DVI-A-1", "DVI"),
            ("card0-VGA-1", "Analog"),
            ("card0-LVDS-1", "LVDS"),
            ("card0-DSI-1", "DSI"),
        ],
    )
    def test_known_connectors(self, dirname, expected):
        path = f"/sys/class/drm/card0/{dirname}"
        assert _parse_connector_type(path) == expected

    def test_unknown_connector_returns_none(self):
        path = "/sys/class/drm/card0/card0-SPI-1"
        assert _parse_connector_type(path) is None

    def test_bare_card_dir_returns_none(self):
        path = "/sys/class/drm/card0"
        assert _parse_connector_type(path) is None

    def test_connector_overrides_edid_interface(self, monkeypatch):
        device_path = "/sys/class/drm/card0/card0-HDMI-A-1"
        edid_path = posixpath.join(device_path, "edid")

        monkeypatch.setattr(posixpath, "exists", lambda p: p == edid_path)
        monkeypatch.setattr(
            builtins,
            "open",
            lambda *a, **kw: mock_open(read_data=b"\x01\x02")(),
        )
        monkeypatch.setattr(
            "hwprobe.core.linux.display.parse_edid",
            lambda _: DisplayModuleInfo(name="Test", interface="DisplayPort"),
        )
        monkeypatch.setattr(
            posixpath,
            "realpath",
            lambda _: "/sys/devices/platform/drm/card0",
        )

        monitor = _fetch_individual_monitor_info(device_path, [])

        assert monitor is not None
        assert monitor.interface == "HDMI"
