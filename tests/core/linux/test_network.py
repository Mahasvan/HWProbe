import builtins
import json
import os
import subprocess
from unittest.mock import mock_open

import pytest

from hwprobe.core.linux.network import _enrich_with_sysfs_info, _fetch_ip_data, fetch_network_info
from hwprobe.models.network_models import NICInfo, NetworkInfo
from hwprobe.models.status_models import Status, StatusType


class TestEnrichWithSysfsInfo:
    DEVICE_PATH = "/sys/class/net/eth0/device"

    def _make_nic(self, interface="eth0"):
        return NICInfo(interface=interface)

    def _patch_exists(self, monkeypatch, paths):
        monkeypatch.setattr(os.path, "exists", lambda p: p in paths)

    def test_no_interface_returns_early(self):
        nic = NICInfo(interface=None)
        status = Status()
        _enrich_with_sysfs_info(nic, status)
        assert nic.vendor_id is None
        assert status.type == StatusType.SUCCESS

    def test_virtual_interface_raises_value_error(self, monkeypatch):
        nic = self._make_nic()
        self._patch_exists(monkeypatch, set())
        status = Status()
        with pytest.raises(ValueError, match="Interface is virtual: eth0"):
            _enrich_with_sysfs_info(nic, status)

    def test_vendor_and_device_read(self, monkeypatch):
        nic = self._make_nic()
        self._patch_exists(monkeypatch, {self.DEVICE_PATH})

        def fake_open(path, *args, **kwargs):
            if path.endswith("/vendor"):
                return mock_open(read_data="0x8086")()
            if path.endswith("/device"):
                return mock_open(read_data="0x1572")()
            if path.endswith("/firmware_node/path"):
                return mock_open(read_data=r"\_SB.PCI0.GLAN")()
            raise FileNotFoundError(path)

        monkeypatch.setattr(builtins, "open", fake_open)
        monkeypatch.setattr(os.path, "realpath", lambda p: "/sys/devices/pci0000:00/0000:00:1f.6")
        monkeypatch.setattr("hwprobe.core.linux.network.pci_path_linux", lambda s: "PciRoot(0x0)/Pci(0x1f,0x6)")

        status = Status()
        _enrich_with_sysfs_info(nic, status)

        assert nic.vendor_id == "0x8086"
        assert nic.device_id == "0x1572"
        assert nic.pci_path == "PciRoot(0x0)/Pci(0x1f,0x6)"
        assert status.type == StatusType.SUCCESS

    def test_missing_vendor_makes_partial(self, monkeypatch):
        nic = self._make_nic()
        self._patch_exists(monkeypatch, {self.DEVICE_PATH})

        def fake_open(path, *args, **kwargs):
            if path.endswith("/vendor"):
                raise FileNotFoundError(path)
            if path.endswith("/device"):
                return mock_open(read_data="0x1572")()
            raise FileNotFoundError(path)

        monkeypatch.setattr(builtins, "open", fake_open)
        monkeypatch.setattr(os.path, "realpath", lambda p: "/sys/devices/pci0000:00/0000:00:1f.6")
        monkeypatch.setattr("hwprobe.core.linux.network.pci_path_linux", lambda s: None)

        status = Status()
        _enrich_with_sysfs_info(nic, status)

        assert nic.vendor_id is None
        assert nic.device_id == "0x1572"
        assert status.type == StatusType.PARTIAL
        assert any("Vendor ID not found" in m for m in status.messages)

    def test_missing_device_makes_partial(self, monkeypatch):
        nic = self._make_nic()
        self._patch_exists(monkeypatch, {self.DEVICE_PATH})

        def fake_open(path, *args, **kwargs):
            if path.endswith("/vendor"):
                return mock_open(read_data="0x8086")()
            if path.endswith("/device"):
                raise FileNotFoundError(path)
            raise FileNotFoundError(path)

        monkeypatch.setattr(builtins, "open", fake_open)
        monkeypatch.setattr(os.path, "realpath", lambda p: "/sys/devices/pci0000:00/0000:00:1f.6")
        monkeypatch.setattr("hwprobe.core.linux.network.pci_path_linux", lambda s: None)

        status = Status()
        _enrich_with_sysfs_info(nic, status)

        assert nic.vendor_id == "0x8086"
        assert nic.device_id is None
        assert status.type == StatusType.PARTIAL
        assert any("Device ID not found" in m for m in status.messages)

    def test_acpi_path_populated(self, monkeypatch):
        nic = self._make_nic()
        self._patch_exists(monkeypatch, {self.DEVICE_PATH})

        def fake_open(path, *args, **kwargs):
            if path.endswith("/vendor"):
                return mock_open(read_data="0x8086")()
            if path.endswith("/device"):
                return mock_open(read_data="0x1572")()
            if path.endswith("/firmware_node/path"):
                return mock_open(read_data=r"\_SB.PCI0.GLAN")()
            raise FileNotFoundError(path)

        monkeypatch.setattr(builtins, "open", fake_open)
        monkeypatch.setattr(os.path, "realpath", lambda p: "/sys/devices/pci0000:00/0000:00:1f.6")
        monkeypatch.setattr("hwprobe.core.linux.network.pci_path_linux", lambda s: None)

        status = Status()
        _enrich_with_sysfs_info(nic, status)

        assert nic.acpi_path == r"\_SB.PCI0.GLAN"

    def test_missing_acpi_path_makes_partial(self, monkeypatch):
        nic = self._make_nic()
        self._patch_exists(monkeypatch, {self.DEVICE_PATH})

        def fake_open(path, *args, **kwargs):
            if path.endswith("/vendor"):
                return mock_open(read_data="0x8086")()
            if path.endswith("/device"):
                return mock_open(read_data="0x1572")()
            raise FileNotFoundError(path)

        monkeypatch.setattr(builtins, "open", fake_open)
        monkeypatch.setattr(os.path, "realpath", lambda p: "/sys/devices/pci0000:00/0000:00:1f.6")
        monkeypatch.setattr("hwprobe.core.linux.network.pci_path_linux", lambda s: None)

        status = Status()
        _enrich_with_sysfs_info(nic, status)

        assert status.type == StatusType.PARTIAL
        assert any("Path not found" in m for m in status.messages)

    def test_pci_path_resolved_from_realpath(self, monkeypatch):
        nic = self._make_nic()
        self._patch_exists(monkeypatch, {self.DEVICE_PATH})

        def fake_open(path, *args, **kwargs):
            if path.endswith("/vendor"):
                return mock_open(read_data="0x8086")()
            if path.endswith("/device"):
                return mock_open(read_data="0x1572")()
            raise FileNotFoundError(path)

        monkeypatch.setattr(builtins, "open", fake_open)
        monkeypatch.setattr(os.path, "realpath", lambda p: "/sys/devices/pci0000:00/0000:01:00.0")

        pci_calls = []
        monkeypatch.setattr(
            "hwprobe.core.linux.network.pci_path_linux",
            lambda s: (pci_calls.append(s), "PciRoot(0x0)/Pci(0x1,0x0)")[-1],
        )

        status = Status()
        _enrich_with_sysfs_info(nic, status)

        assert pci_calls == ["0000:01:00.0"]
        assert nic.pci_path == "PciRoot(0x0)/Pci(0x1,0x0)"


class TestFetchIpData:
    def _mock_ip_output(self, rows):
        return json.dumps(rows).encode()

    def test_single_ethernet_interface(self, monkeypatch):
        rows = [
            {
                "ifname": "eth0",
                "link_type": "ether",
                "address": "aa:bb:cc:dd:ee:ff",
                "addr_info": [{"family": "inet", "local": "192.168.1.10"}],
            }
        ]
        monkeypatch.setattr(subprocess, "check_output", lambda *a, **kw: self._mock_ip_output(rows))
        monkeypatch.setattr(os.path, "exists", lambda p: False)  # virtual -> skipped enrichment

        info = _fetch_ip_data()
        assert len(info.modules) == 0  # virtual interface, skipped

    def test_physical_interface_enriched(self, monkeypatch):
        rows = [
            {
                "ifname": "eth0",
                "link_type": "ether",
                "address": "aa:bb:cc:dd:ee:ff",
                "addr_info": [{"family": "inet", "local": "10.0.0.5"}],
            }
        ]
        monkeypatch.setattr(subprocess, "check_output", lambda *a, **kw: self._mock_ip_output(rows))
        monkeypatch.setattr(os.path, "exists", lambda p: p == "/sys/class/net/eth0/device")

        def fake_open(path, *args, **kwargs):
            if path.endswith("/vendor"):
                return mock_open(read_data="0x8086")()
            if path.endswith("/device"):
                return mock_open(read_data="0x1572")()
            raise FileNotFoundError(path)

        monkeypatch.setattr(builtins, "open", fake_open)
        monkeypatch.setattr(os.path, "realpath", lambda p: "/sys/devices/pci0000:00/0000:00:1f.6")
        monkeypatch.setattr("hwprobe.core.linux.network.pci_path_linux", lambda s: None)

        info = _fetch_ip_data()
        assert len(info.modules) == 1
        nic = info.modules[0]
        assert nic.interface == "eth0"
        assert nic.type == "ether"
        assert nic.mac_address == "aa:bb:cc:dd:ee:ff"
        assert nic.ip_address == "10.0.0.5"
        assert nic.vendor_id == "0x8086"
        assert nic.device_id == "0x1572"

    def test_ipv4_preferred_over_ipv6(self, monkeypatch):
        rows = [
            {
                "ifname": "eth0",
                "link_type": "ether",
                "address": "aa:bb:cc:dd:ee:ff",
                "addr_info": [
                    {"family": "inet6", "local": "fe80::1"},
                    {"family": "inet", "local": "172.16.0.2"},
                ],
            }
        ]
        monkeypatch.setattr(subprocess, "check_output", lambda *a, **kw: self._mock_ip_output(rows))
        monkeypatch.setattr(os.path, "exists", lambda p: p == "/sys/class/net/eth0/device")

        def fake_open(path, *args, **kwargs):
            if path.endswith("/vendor"):
                return mock_open(read_data="0x10ec")()
            if path.endswith("/device"):
                return mock_open(read_data="0x8168")()
            raise FileNotFoundError(path)

        monkeypatch.setattr(builtins, "open", fake_open)
        monkeypatch.setattr(os.path, "realpath", lambda p: "/sys/devices/pci0000:00/0000:00:1f.6")
        monkeypatch.setattr("hwprobe.core.linux.network.pci_path_linux", lambda s: None)

        info = _fetch_ip_data()
        assert info.modules[0].ip_address == "172.16.0.2"

    def test_ipv6_fallback_when_no_ipv4(self, monkeypatch):
        rows = [
            {
                "ifname": "eth0",
                "link_type": "ether",
                "address": "aa:bb:cc:dd:ee:ff",
                "addr_info": [{"family": "inet6", "local": "fe80::abcd"}],
            }
        ]
        monkeypatch.setattr(subprocess, "check_output", lambda *a, **kw: self._mock_ip_output(rows))
        monkeypatch.setattr(os.path, "exists", lambda p: p == "/sys/class/net/eth0/device")

        def fake_open(path, *args, **kwargs):
            if path.endswith("/vendor"):
                return mock_open(read_data="0x10ec")()
            if path.endswith("/device"):
                return mock_open(read_data="0x8168")()
            raise FileNotFoundError(path)

        monkeypatch.setattr(builtins, "open", fake_open)
        monkeypatch.setattr(os.path, "realpath", lambda p: "/sys/devices/pci0000:00/0000:00:1f.6")
        monkeypatch.setattr("hwprobe.core.linux.network.pci_path_linux", lambda s: None)

        info = _fetch_ip_data()
        assert info.modules[0].ip_address == "fe80::abcd"

    def test_no_ip_address(self, monkeypatch):
        rows = [
            {
                "ifname": "eth0",
                "link_type": "ether",
                "address": "aa:bb:cc:dd:ee:ff",
                "addr_info": [],
            }
        ]
        monkeypatch.setattr(subprocess, "check_output", lambda *a, **kw: self._mock_ip_output(rows))
        monkeypatch.setattr(os.path, "exists", lambda p: p == "/sys/class/net/eth0/device")

        def fake_open(path, *args, **kwargs):
            if path.endswith("/vendor"):
                return mock_open(read_data="0x10ec")()
            if path.endswith("/device"):
                return mock_open(read_data="0x8168")()
            raise FileNotFoundError(path)

        monkeypatch.setattr(builtins, "open", fake_open)
        monkeypatch.setattr(os.path, "realpath", lambda p: "/sys/devices/pci0000:00/0000:00:1f.6")
        monkeypatch.setattr("hwprobe.core.linux.network.pci_path_linux", lambda s: None)

        info = _fetch_ip_data()
        assert info.modules[0].ip_address is None

    def test_multiple_interfaces(self, monkeypatch):
        rows = [
            {
                "ifname": "eth0",
                "link_type": "ether",
                "address": "aa:bb:cc:dd:ee:ff",
                "addr_info": [{"family": "inet", "local": "10.0.0.1"}],
            },
            {
                "ifname": "wlan0",
                "link_type": "ether",
                "address": "11:22:33:44:55:66",
                "addr_info": [{"family": "inet", "local": "10.0.0.2"}],
            },
        ]
        monkeypatch.setattr(subprocess, "check_output", lambda *a, **kw: self._mock_ip_output(rows))
        monkeypatch.setattr(os.path, "exists", lambda p: p in {
            "/sys/class/net/eth0/device",
            "/sys/class/net/wlan0/device",
        })

        def fake_open(path, *args, **kwargs):
            if path.endswith("/vendor"):
                return mock_open(read_data="0x8086")()
            if path.endswith("/device"):
                return mock_open(read_data="0x1572")()
            raise FileNotFoundError(path)

        monkeypatch.setattr(builtins, "open", fake_open)
        monkeypatch.setattr(os.path, "realpath", lambda p: "/sys/devices/pci0000:00/0000:00:1f.6")
        monkeypatch.setattr("hwprobe.core.linux.network.pci_path_linux", lambda s: None)

        info = _fetch_ip_data()
        assert len(info.modules) == 2
        assert {m.interface for m in info.modules} == {"eth0", "wlan0"}

    def test_virtual_interfaces_skipped(self, monkeypatch):
        rows = [
            {"ifname": "lo", "link_type": "loopback", "address": "00:00:00:00:00:00", "addr_info": []},
            {"ifname": "docker0", "link_type": "ether", "address": "02:42:00:00:00:00", "addr_info": []},
        ]
        monkeypatch.setattr(subprocess, "check_output", lambda *a, **kw: self._mock_ip_output(rows))
        monkeypatch.setattr(os.path, "exists", lambda p: False)

        info = _fetch_ip_data()
        assert len(info.modules) == 0

    def test_mixed_virtual_and_physical(self, monkeypatch):
        rows = [
            {"ifname": "lo", "link_type": "loopback", "address": "00:00:00:00:00:00", "addr_info": []},
            {
                "ifname": "eth0",
                "link_type": "ether",
                "address": "aa:bb:cc:dd:ee:ff",
                "addr_info": [{"family": "inet", "local": "10.0.0.1"}],
            },
        ]
        monkeypatch.setattr(subprocess, "check_output", lambda *a, **kw: self._mock_ip_output(rows))
        monkeypatch.setattr(os.path, "exists", lambda p: p == "/sys/class/net/eth0/device")

        def fake_open(path, *args, **kwargs):
            if path.endswith("/vendor"):
                return mock_open(read_data="0x8086")()
            if path.endswith("/device"):
                return mock_open(read_data="0x1572")()
            raise FileNotFoundError(path)

        monkeypatch.setattr(builtins, "open", fake_open)
        monkeypatch.setattr(os.path, "realpath", lambda p: "/sys/devices/pci0000:00/0000:00:1f.6")
        monkeypatch.setattr("hwprobe.core.linux.network.pci_path_linux", lambda s: None)

        info = _fetch_ip_data()
        assert len(info.modules) == 1
        assert info.modules[0].interface == "eth0"

    def test_missing_ifname_skipped(self, monkeypatch):
        rows = [
            {"link_type": "ether", "address": "aa:bb:cc:dd:ee:ff", "addr_info": []},
        ]
        monkeypatch.setattr(subprocess, "check_output", lambda *a, **kw: self._mock_ip_output(rows))
        monkeypatch.setattr(os.path, "exists", lambda p: False)

        info = _fetch_ip_data()
        assert len(info.modules) == 0

    def test_empty_addr_info_list(self, monkeypatch):
        rows = [
            {
                "ifname": "eth0",
                "link_type": "ether",
                "address": "aa:bb:cc:dd:ee:ff",
                "addr_info": [],
            }
        ]
        monkeypatch.setattr(subprocess, "check_output", lambda *a, **kw: self._mock_ip_output(rows))
        monkeypatch.setattr(os.path, "exists", lambda p: p == "/sys/class/net/eth0/device")

        def fake_open(path, *args, **kwargs):
            if path.endswith("/vendor"):
                return mock_open(read_data="0x8086")()
            if path.endswith("/device"):
                return mock_open(read_data="0x1572")()
            raise FileNotFoundError(path)

        monkeypatch.setattr(builtins, "open", fake_open)
        monkeypatch.setattr(os.path, "realpath", lambda p: "/sys/devices/pci0000:00/0000:00:1f.6")
        monkeypatch.setattr("hwprobe.core.linux.network.pci_path_linux", lambda s: None)

        info = _fetch_ip_data()
        assert info.modules[0].ip_address is None


class TestFetchNetworkInfo:
    def test_returns_network_info_type(self, monkeypatch):
        monkeypatch.setattr(
            "hwprobe.core.linux.network._fetch_ip_data",
            lambda: NetworkInfo(),
        )
        info = fetch_network_info()
        assert isinstance(info, NetworkInfo)
        assert info.modules == []

    def test_propagates_modules(self, monkeypatch):
        nic = NICInfo(interface="eth0", mac_address="aa:bb:cc:dd:ee:ff")
        expected = NetworkInfo(modules=[nic])
        monkeypatch.setattr(
            "hwprobe.core.linux.network._fetch_ip_data",
            lambda: expected,
        )
        info = fetch_network_info()
        assert len(info.modules) == 1
        assert info.modules[0].interface == "eth0"
