import plistlib
from unittest.mock import MagicMock, patch

import pytest

from hwprobe.core.mac.network import (
    _fetch_airport_details,
    _fetch_controllers,
    _fetch_ethernet_details,
    _fetch_system_profiler_details,
    _find_child,
    _get_bsd_interface_apple_silicon,
    fetch_network_info,
)
from hwprobe.models.network_models import NetworkInfo, NICInfo

# ── helpers ──────────────────────────────────────────────────────────────────


def _make_subprocess_result(stdout_str="", stdout_bytes=None):
    mock_result = MagicMock()
    if stdout_bytes is not None:
        mock_result.stdout = stdout_bytes
    else:
        mock_result.stdout = stdout_str.encode()
    return mock_result


def _make_network_plist(items):
    """Build a fake SPNetworkDataType plist structure."""
    return plistlib.dumps([{"_items": items}], fmt=plistlib.FMT_XML)


def _make_ethernet_plist(items):
    """Build a fake SPEthernetDataType plist structure."""
    return plistlib.dumps([{"_items": items}], fmt=plistlib.FMT_XML)


def _make_ioreg_plist(items):
    """Build a fake ioreg IO80211Controller plist (list of controller dicts)."""
    return plistlib.dumps(items, fmt=plistlib.FMT_XML)


def _make_intel_ioreg_entry(
    io_name_matched="pci14e4,4331",
    io_model="AirPort Extreme",
    bsd_name="en1",
):
    """AirPort_BrcmNIC entry as seen on Intel Macs."""
    return {
        "IORegistryEntryName": "AirPort_BrcmNIC",
        "IONameMatched": io_name_matched,
        "IOModel": io_model,
        "IORegistryEntryChildren": [
            {
                "IOObjectClass": "AirPort_BrcmNIC_Interface",
                "IORegistryEntryName": bsd_name,
            }
        ],
    }


def _make_apple_silicon_ioreg_entry(
    manufacturer_id=0x14E4,
    product_id=0x4488,
    bsd_name="en0",
):
    """AppleBCMWLANCore entry as seen on Apple Silicon Macs."""
    return {
        "IORegistryEntryName": "AppleBCMWLANCore",
        "ModuleDictionary": {
            "ManufacturerID": manufacturer_id,
            "ProductID": product_id,
        },
        "IORegistryEntryChildren": [
            {
                "IORegistryEntryName": "AppleBCMWLANSkywalkInterface",
                "IORegistryEntryChildren": [
                    {
                        "IOObjectClass": "IOSkywalkLegacyEthernet",
                        "IORegistryEntryChildren": [
                            {
                                "IOObjectClass": "IOSkywalkLegacyEthernetInterface",
                                "IORegistryEntryName": bsd_name,
                            }
                        ],
                    }
                ],
            }
        ],
    }


def _make_brcm4331_ioreg_entry(
    io_name_matched="pci14e4,4331",
    io_model="Wireless Network Adapter (802.11 a/b/g/n)",
    bsd_name="en1",
):
    """AirPort_Brcm4331 entry as seen on older Intel Macs."""
    return {
        "IORegistryEntryName": "AirPort_Brcm4331",
        "IONameMatched": io_name_matched,
        "IOModel": io_model,
        "IORegistryEntryChildren": [
            {
                "IOObjectClass": bsd_name,
                "IORegistryEntryName": bsd_name,
            }
        ],
    }


# ── _fetch_controllers ───────────────────────────────────────────────────────


class TestFetchControllers:
    @patch("hwprobe.core.mac.network.subprocess.run")
    def test_returns_interface_list(self, mock_run):
        mock_run.return_value = _make_subprocess_result("en0 en1 en2")
        result = _fetch_controllers()
        assert result == ["en0", "en1", "en2"]

    @patch("hwprobe.core.mac.network.subprocess.run")
    def test_single_interface(self, mock_run):
        mock_run.return_value = _make_subprocess_result("en0")
        result = _fetch_controllers()
        assert result == ["en0"]

    @patch("hwprobe.core.mac.network.subprocess.run")
    def test_empty_output_returns_empty_list(self, mock_run):
        mock_run.return_value = _make_subprocess_result("")
        result = _fetch_controllers()
        assert result == []

    @patch("hwprobe.core.mac.network.subprocess.run")
    def test_subprocess_failure_propagates(self, mock_run):
        """
        BUG 2: No try/except around subprocess call.
        """
        mock_run.side_effect = FileNotFoundError("ipconfig not found")
        with pytest.raises(FileNotFoundError):
            _fetch_controllers()


# ── _fetch_ethernet_details ──────────────────────────────────────────────────


class TestFetchEthernetDetails:
    @patch("hwprobe.core.mac.network.subprocess.run")
    def test_single_ethernet_controller(self, mock_run):
        plist_data = _make_ethernet_plist(
            [
                {
                    "spethernet_BSD_Device_Name": "en0",
                    "spethernet_vendor-id": "0x8086",
                    "spethernet_vendor_name": "Intel",
                    "spethernet_product-id": "0x15B8",
                }
            ]
        )
        mock_run.return_value = MagicMock(stdout=plist_data)

        result = _fetch_ethernet_details()
        assert "en0" in result
        assert result["en0"].vendor_id == "0x8086"
        assert result["en0"].manufacturer == "Intel"
        assert result["en0"].device_id == "0x15B8"

    @patch("hwprobe.core.mac.network.subprocess.run")
    def test_multiple_ethernet_controllers(self, mock_run):
        plist_data = _make_ethernet_plist(
            [
                {
                    "spethernet_BSD_Device_Name": "en0",
                    "spethernet_vendor-id": "0x8086",
                    "spethernet_vendor_name": "Intel",
                    "spethernet_product-id": "0x15B8",
                },
                {
                    "spethernet_BSD_Device_Name": "en3",
                    "spethernet_vendor-id": "0x14e4",
                    "spethernet_vendor_name": "Broadcom",
                    "spethernet_product-id": "0x1682",
                },
            ]
        )
        mock_run.return_value = MagicMock(stdout=plist_data)

        result = _fetch_ethernet_details()
        assert len(result) == 2
        assert "en0" in result
        assert "en3" in result

    @patch("hwprobe.core.mac.network.subprocess.run")
    def test_subprocess_failure_propagates(self, mock_run):
        """BUG 2: No error handling in _fetch_ethernet_details."""
        mock_run.side_effect = FileNotFoundError("system_profiler not found")
        with pytest.raises(FileNotFoundError):
            _fetch_ethernet_details()


# ── _find_child ──────────────────────────────────────────────────────────────


class TestFindChild:
    def test_returns_matching_dict(self):
        children = [
            {"IOObjectClass": "Foo"},
            {"IOObjectClass": "Bar"},
        ]
        result = _find_child(children, "IOObjectClass", "Bar")
        assert result == {"IOObjectClass": "Bar"}

    def test_returns_none_when_no_match(self):
        children = [{"IOObjectClass": "Foo"}]
        result = _find_child(children, "IOObjectClass", "Missing")
        assert result is None

    def test_returns_none_for_empty_list(self):
        assert _find_child([], "IOObjectClass", "Foo") is None

    def test_skips_falsy_entries(self):
        children = [None, {}, {"IOObjectClass": "Target"}]
        result = _find_child(children, "IOObjectClass", "Target")
        assert result == {"IOObjectClass": "Target"}

    def test_returns_first_match(self):
        children = [
            {"IOObjectClass": "Target", "id": 1},
            {"IOObjectClass": "Target", "id": 2},
        ]
        result = _find_child(children, "IOObjectClass", "Target")
        assert result["id"] == 1


# ── _get_bsd_interface_apple_silicon ─────────────────────────────────────────


class TestGetBsdInterfaceAppleSilicon:
    def _make_item(self, bsd_name="en0"):
        return _make_apple_silicon_ioreg_entry(bsd_name=bsd_name)

    def test_returns_bsd_name_for_full_path(self):
        item = self._make_item("en0")
        assert _get_bsd_interface_apple_silicon(item) == "en0"

    def test_returns_none_when_skywalk_interface_missing(self):
        item = {"IORegistryEntryChildren": []}
        assert _get_bsd_interface_apple_silicon(item) is None

    def test_returns_none_when_legacy_ethernet_missing(self):
        item = {
            "IORegistryEntryChildren": [
                {
                    "IORegistryEntryName": "AppleBCMWLANSkywalkInterface",
                    "IORegistryEntryChildren": [],  # no IOSkywalkLegacyEthernet
                }
            ]
        }
        assert _get_bsd_interface_apple_silicon(item) is None

    def test_returns_none_when_legacy_interface_missing(self):
        item = {
            "IORegistryEntryChildren": [
                {
                    "IORegistryEntryName": "AppleBCMWLANSkywalkInterface",
                    "IORegistryEntryChildren": [
                        {
                            "IOObjectClass": "IOSkywalkLegacyEthernet",
                            "IORegistryEntryChildren": [],  # no IOSkywalkLegacyEthernetInterface
                        }
                    ],
                }
            ]
        }
        assert _get_bsd_interface_apple_silicon(item) is None

    def test_returns_none_when_children_key_absent(self):
        assert _get_bsd_interface_apple_silicon({}) is None


# ── _fetch_airport_details ───────────────────────────────────────────────────


class TestFetchAirportDetails:
    @patch("hwprobe.core.mac.network.subprocess.run")
    def test_intel_mac_brcm_nic(self, mock_run):
        """AirPort_BrcmNIC entry is parsed correctly on Intel Macs."""
        plist_data = _make_ioreg_plist(
            [
                _make_intel_ioreg_entry(
                    io_name_matched="pci14e4,4331",
                    io_model="AirPort Extreme",
                    bsd_name="en1",
                )
            ]
        )
        mock_run.return_value = MagicMock(stdout=plist_data)

        result = _fetch_airport_details()
        assert "en1" in result
        assert result["en1"].vendor_id == "0x14e4"
        assert result["en1"].device_id == "0x4331"
        assert result["en1"].name == "AirPort Extreme"

    @patch("hwprobe.core.mac.network.subprocess.run")
    def test_intel_mac_vendor_device_uppercased(self, mock_run):
        """Vendor and device IDs are stored as uppercase hex strings."""
        plist_data = _make_ioreg_plist(
            [
                _make_intel_ioreg_entry(
                    io_name_matched="pci8086,095a",
                )
            ]
        )
        mock_run.return_value = MagicMock(stdout=plist_data)

        result = _fetch_airport_details()
        assert result["en1"].vendor_id == "0x8086"
        assert result["en1"].device_id == "0x095a"

    @patch("hwprobe.core.mac.network.subprocess.run")
    def test_intel_mac_no_matching_interface_child(self, mock_run):
        """Entry with no AirPort_BrcmNIC_Interface child produces no result."""
        entry = {
            "IORegistryEntryName": "AirPort_BrcmNIC",
            "IONameMatched": "pci14e4,4331",
            "IOModel": "AirPort Extreme",
            "IORegistryEntryChildren": [],  # no matching child
        }
        plist_data = _make_ioreg_plist([entry])
        mock_run.return_value = MagicMock(stdout=plist_data)

        result = _fetch_airport_details()
        assert result == {}

    @patch("hwprobe.core.mac.network.subprocess.run")
    def test_apple_silicon_bcm_wlan_core(self, mock_run):
        """AppleBCMWLANCore entry is parsed correctly on Apple Silicon Macs."""
        plist_data = _make_ioreg_plist(
            [
                _make_apple_silicon_ioreg_entry(
                    manufacturer_id=0x14E4,
                    product_id=0x4488,
                    bsd_name="en0",
                )
            ]
        )
        mock_run.return_value = MagicMock(stdout=plist_data)

        result = _fetch_airport_details()
        assert "en0" in result
        # hex(0x14e4).upper() → "0x14e4" (the X is uppercased too)
        assert result["en0"].vendor_id == "0x14e4"
        assert result["en0"].device_id == "0x4488"

    @patch("hwprobe.core.mac.network.subprocess.run")
    def test_apple_silicon_no_bsd_interface_skipped(self, mock_run):
        """Apple Silicon entry with no resolvable BSD interface is not added."""
        entry = {
            "IORegistryEntryName": "AppleBCMWLANCore",
            "ModuleDictionary": {"ManufacturerID": 0x14E4, "ProductID": 0x4488},
            "IORegistryEntryChildren": [],  # missing Skywalk tree
        }
        plist_data = _make_ioreg_plist([entry])
        mock_run.return_value = MagicMock(stdout=plist_data)

        result = _fetch_airport_details()
        assert result == {}

    @patch("hwprobe.core.mac.network.subprocess.run")
    def test_brcm4331_driver(self, mock_run):
        """AirPort_Brcm4331 entry is parsed correctly on older Intel Macs."""
        plist_data = _make_ioreg_plist(
            [
                _make_brcm4331_ioreg_entry(
                    io_name_matched="pci14e4,4331",
                    io_model="Wireless Network Adapter (802.11 a/b/g/n)",
                    bsd_name="en1",
                )
            ]
        )
        mock_run.return_value = MagicMock(stdout=plist_data)

        result = _fetch_airport_details()
        assert "en1" in result
        assert result["en1"].vendor_id == "0x14e4"
        assert result["en1"].device_id == "0x4331"
        assert result["en1"].name == "Wireless Network Adapter (802.11 a/b/g/n)"

    @patch("hwprobe.core.mac.network.subprocess.run")
    def test_brcm4331_alternate_device_id(self, mock_run):
        """AirPort_Brcm4331 supports multiple device IDs (4331, 4353, 432b)."""
        plist_data = _make_ioreg_plist(
            [
                _make_brcm4331_ioreg_entry(
                    io_name_matched="pci14e4,4353",
                    bsd_name="en1",
                )
            ]
        )
        mock_run.return_value = MagicMock(stdout=plist_data)

        result = _fetch_airport_details()
        assert "en1" in result
        assert result["en1"].vendor_id == "0x14e4"
        assert result["en1"].device_id == "0x4353"

    @patch("hwprobe.core.mac.network.subprocess.run")
    def test_brcm4331_no_model(self, mock_run):
        """AirPort_Brcm4331 without IOModel still extracts vendor/device IDs."""
        entry = _make_brcm4331_ioreg_entry(bsd_name="en1")
        del entry["IOModel"]
        plist_data = _make_ioreg_plist([entry])
        mock_run.return_value = MagicMock(stdout=plist_data)

        result = _fetch_airport_details()
        assert "en1" in result
        assert result["en1"].vendor_id == "0x14e4"
        assert result["en1"].device_id == "0x4331"
        assert result["en1"].name is None

    @patch("hwprobe.core.mac.network.subprocess.run")
    def test_brcm4331_no_matching_child(self, mock_run):
        """AirPort_Brcm4331 entry with no en* child produces no result."""
        entry = {
            "IORegistryEntryName": "AirPort_Brcm4331",
            "IONameMatched": "pci14e4,4331",
            "IOModel": "Wireless Network Adapter",
            "IORegistryEntryChildren": [],
        }
        plist_data = _make_ioreg_plist([entry])
        mock_run.return_value = MagicMock(stdout=plist_data)

        result = _fetch_airport_details()
        assert result == {}

    @patch("hwprobe.core.mac.network.subprocess.run")
    def test_brcm4331_no_regex_match(self, mock_run):
        """AirPort_Brcm4331 with malformed IONameMatched is skipped."""
        entry = {
            "IORegistryEntryName": "AirPort_Brcm4331",
            "IONameMatched": "invalid-format",
            "IOModel": "Wireless Network Adapter",
            "IORegistryEntryChildren": [{"IOObjectClass": "en1", "IORegistryEntryName": "en1"}],
        }
        plist_data = _make_ioreg_plist([entry])
        mock_run.return_value = MagicMock(stdout=plist_data)

        result = _fetch_airport_details()
        assert result == {}

    @patch("hwprobe.core.mac.network.subprocess.run")
    def test_unknown_driver_is_skipped(self, mock_run):
        """Unknown drivers print a warning and are skipped — no exception raised."""
        entry = {"IORegistryEntryName": "AirPortAtheros40"}
        plist_data = _make_ioreg_plist([entry])
        mock_run.return_value = MagicMock(stdout=plist_data)

        result = _fetch_airport_details()
        assert result == {}

    @patch("hwprobe.core.mac.network.subprocess.run")
    def test_missing_driver_name_returns_early(self, mock_run):
        """Entry without IORegistryEntryName causes early return with empty result."""
        plist_data = _make_ioreg_plist([{"IONameMatched": "pci14e4,4331"}])
        mock_run.return_value = MagicMock(stdout=plist_data)

        result = _fetch_airport_details()
        assert result == {}

    @patch("hwprobe.core.mac.network.subprocess.run")
    def test_multiple_controllers(self, mock_run):
        """Multiple controllers across both Mac types are all collected."""
        plist_data = _make_ioreg_plist(
            [
                _make_intel_ioreg_entry(bsd_name="en1"),
                _make_apple_silicon_ioreg_entry(bsd_name="en0"),
            ]
        )
        mock_run.return_value = MagicMock(stdout=plist_data)

        result = _fetch_airport_details()
        assert "en0" in result
        assert "en1" in result

    @patch("hwprobe.core.mac.network.subprocess.run")
    def test_subprocess_failure_propagates(self, mock_run):
        mock_run.side_effect = FileNotFoundError("ioreg not found")
        with pytest.raises(FileNotFoundError):
            _fetch_airport_details()


# ── _fetch_system_profiler_details ───────────────────────────────────────────


class TestFetchSystemProfilerDetails:
    @patch("hwprobe.core.mac.network._fetch_ethernet_details")
    @patch("hwprobe.core.mac.network.subprocess.run")
    def test_single_ethernet_nic(self, mock_run, mock_eth):
        network_plist = _make_network_plist(
            [
                {
                    "interface": "en0",
                    "_name": "Ethernet",
                    "Ethernet": {"MAC Address": "aa:bb:cc:dd:ee:ff"},
                    "type": "Ethernet",
                    "IPv4": {"Addresses": ["192.168.1.100"]},
                }
            ]
        )
        mock_run.return_value = MagicMock(stdout=network_plist)
        mock_eth.return_value = {"en0": NICInfo(vendor_id="0x8086", manufacturer="Intel", device_id="0x15B8")}

        result = _fetch_system_profiler_details(["en0"])
        assert len(result.modules) == 1
        m = result.modules[0]
        assert m.interface == "en0"
        assert m.name == "Ethernet"
        assert m.mac_address == "aa:bb:cc:dd:ee:ff"
        assert m.type == "Ethernet"
        assert m.ip_address == "192.168.1.100"
        assert m.vendor_id == "0x8086"
        assert m.manufacturer == "Intel"

    @patch("hwprobe.core.mac.network._fetch_airport_details")
    @patch("hwprobe.core.mac.network.subprocess.run")
    def test_single_wifi_nic(self, mock_run, mock_air):
        network_plist = _make_network_plist(
            [
                {
                    "interface": "en1",
                    "_name": "Wi-Fi",
                    "Ethernet": {"MAC Address": "11:22:33:44:55:66"},
                    "type": "AirPort",
                }
            ]
        )
        mock_run.return_value = MagicMock(stdout=network_plist)
        mock_air.return_value = {"en1": NICInfo(vendor_id="0x14e4", device_id="0x4331")}

        result = _fetch_system_profiler_details(["en1"])
        assert len(result.modules) == 1
        m = result.modules[0]
        assert m.type == "AirPort"
        assert m.vendor_id == "0x14e4"

    @patch("hwprobe.core.mac.network.subprocess.run")
    def test_interface_not_in_valid_list_is_skipped(self, mock_run):
        network_plist = _make_network_plist(
            [
                {
                    "interface": "en5",
                    "_name": "USB Ethernet",
                    "Ethernet": {"MAC Address": "aa:bb:cc:dd:ee:ff"},
                    "type": "Ethernet",
                }
            ]
        )
        mock_run.return_value = MagicMock(stdout=network_plist)

        result = _fetch_system_profiler_details(["en0", "en1"])
        assert result.modules == []

    @patch("hwprobe.core.mac.network.subprocess.run")
    def test_no_mac_address_skipped(self, mock_run):
        """Devices without MAC address are skipped (unplugged devices)."""
        network_plist = _make_network_plist(
            [
                {
                    "interface": "en0",
                    "_name": "Ethernet",
                    "type": "Ethernet",
                }
            ]
        )
        mock_run.return_value = MagicMock(stdout=network_plist)

        result = _fetch_system_profiler_details(["en0"])
        assert result.modules == []

    @patch("hwprobe.core.mac.network.subprocess.run")
    def test_no_ip_address_still_included(self, mock_run):
        network_plist = _make_network_plist(
            [
                {
                    "interface": "en0",
                    "_name": "Ethernet",
                    "Ethernet": {"MAC Address": "aa:bb:cc:dd:ee:ff"},
                    "type": "Ethernet",
                }
            ]
        )
        mock_run.return_value = MagicMock(stdout=network_plist)

        result = _fetch_system_profiler_details(["en0"])
        assert len(result.modules) == 1
        assert result.modules[0].ip_address is None

    @patch("hwprobe.core.mac.network._fetch_ethernet_details")
    @patch("hwprobe.core.mac.network._fetch_airport_details")
    @patch("hwprobe.core.mac.network.subprocess.run")
    def test_mixed_ethernet_and_wifi(self, mock_run, mock_air, mock_eth):
        network_plist = _make_network_plist(
            [
                {
                    "interface": "en0",
                    "_name": "Ethernet",
                    "Ethernet": {"MAC Address": "aa:bb:cc:dd:ee:ff"},
                    "type": "Ethernet",
                },
                {
                    "interface": "en1",
                    "_name": "Wi-Fi",
                    "Ethernet": {"MAC Address": "11:22:33:44:55:66"},
                    "type": "AirPort",
                },
            ]
        )
        mock_run.return_value = MagicMock(stdout=network_plist)
        mock_eth.return_value = {"en0": NICInfo(vendor_id="0x8086")}
        mock_air.return_value = {"en1": NICInfo(vendor_id="0x14e4")}

        result = _fetch_system_profiler_details(["en0", "en1"])
        assert len(result.modules) == 2


# ── Missing _items key handled gracefully ─────────────────────────────────


class TestMissingItemsKey:
    @patch("hwprobe.core.mac.network.subprocess.run")
    def test_missing_items_key_returns_empty(self, mock_run):
        bad_plist = plistlib.dumps([{"not_items": [{"interface": "en0"}]}], fmt=plistlib.FMT_XML)
        mock_run.return_value = MagicMock(stdout=bad_plist)

        result = _fetch_system_profiler_details(["en0"])
        assert result.modules == []


# ── Empty controller list ─────────────────────────────────────────────────


class TestEmptyControllers:
    @patch("hwprobe.core.mac.network.subprocess.run")
    def test_empty_controllers_passes_empty_list(self, mock_run):
        def side_effect(cmd, **kwargs):
            if cmd == ["ipconfig", "getiflist"]:
                return _make_subprocess_result("")
            if cmd[0] == "system_profiler":
                return MagicMock(stdout=_make_network_plist([]))
            raise FileNotFoundError(f"Unexpected: {cmd}")

        mock_run.side_effect = side_effect

        result = fetch_network_info()
        assert isinstance(result, NetworkInfo)
        assert result.modules == []


# ── fetch_network_info ───────────────────────────────────────────────────────


class TestFetchNetworkInfo:
    @patch("hwprobe.core.mac.network.subprocess.run")
    def test_returns_network_info_type(self, mock_run):
        def side_effect(cmd, **kwargs):
            if cmd == ["ipconfig", "getiflist"]:
                return _make_subprocess_result("en0")
            if cmd[0] == "system_profiler":
                return MagicMock(stdout=_make_network_plist([]))
            raise FileNotFoundError(f"Unexpected: {cmd}")

        mock_run.side_effect = side_effect

        result = fetch_network_info()
        assert isinstance(result, NetworkInfo)

    @patch("hwprobe.core.mac.network.subprocess.run")
    def test_ipconfig_failure_propagates(self, mock_run):
        """BUG 2: No error handling around subprocess calls in fetch_network_info."""
        mock_run.side_effect = FileNotFoundError("ipconfig not found")
        with pytest.raises(FileNotFoundError):
            fetch_network_info()
