import posixpath

import pytest

from hwprobe.core.linux.common import _format_pci_component, pci_path_linux


class TestPciPathLinux:
    def test_single_device(self, monkeypatch):
        monkeypatch.setattr(
            posixpath,
            "realpath",
            lambda _: "/sys/devices/pci0000:00/0000:00:02.0",
        )
        assert pci_path_linux("0000:00:02.0") == "PciRoot(0x0)/Pci(0x2,0x0)"

    def test_bridge_chain(self, monkeypatch):
        monkeypatch.setattr(
            posixpath,
            "realpath",
            lambda _: "/sys/devices/pci0000:00/0000:00:01.0/0000:01:00.0",
        )
        assert pci_path_linux("0000:01:00.0") == "PciRoot(0x0)/Pci(0x1,0x0)/Pci(0x0,0x0)"

    def test_multifunction_device(self, monkeypatch):
        monkeypatch.setattr(
            posixpath,
            "realpath",
            lambda _: "/sys/devices/pci0000:00/0000:00:1f.3",
        )
        assert pci_path_linux("0000:00:1f.3") == "PciRoot(0x0)/Pci(0x1f,0x3)"

    def test_non_zero_domain(self, monkeypatch):
        monkeypatch.setattr(
            posixpath,
            "realpath",
            lambda _: "/sys/devices/pci0001:00/0001:00:00.0",
        )
        assert pci_path_linux("0001:00:00.0") == "PciRoot(0x1)/Pci(0x0,0x0)"

    def test_fallback_when_sysfs_has_no_pci(self, monkeypatch):
        monkeypatch.setattr(
            posixpath,
            "realpath",
            lambda _: "/sys/devices/platform/non-pci-device",
        )
        assert pci_path_linux("0000:03:00.0") == "PciRoot(0x0)/Pci(0x0,0x0)"

    @pytest.mark.parametrize("bad_slot", ["", "xyz", ":::"])
    def test_invalid_device_slot_returns_none(self, bad_slot, monkeypatch):
        monkeypatch.setattr(posixpath, "realpath", lambda _: "")
        assert pci_path_linux(bad_slot) is None


class TestFormatPciComponent:
    def test_standard_slot(self):
        assert _format_pci_component("0000:00:02.0") == "0x2,0x0"

    def test_multifunction_slot(self):
        assert _format_pci_component("0000:00:1f.3") == "0x1f,0x3"

    @pytest.mark.parametrize("bad_input", ["", "no-dot", None])
    def test_invalid_input_returns_none(self, bad_input):
        assert _format_pci_component(bad_input) is None
