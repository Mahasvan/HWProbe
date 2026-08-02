import importlib
import importlib.util
import pathlib
import sys
from unittest.mock import MagicMock, patch

import pytest

from hwprobe.models.network_models import NetworkInfo, NICInfo
from hwprobe.models.status_models import StatusType

_MODULE_PATH = pathlib.Path(__file__).resolve().parents[3] / "src" / "hwprobe" / "core" / "windows" / "network.py"
_COMMON_PATH = pathlib.Path(__file__).resolve().parents[3] / "src" / "hwprobe" / "core" / "windows" / "common.py"


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


def _load_network_module():
    """Load network.py directly without triggering core.windows.__init__."""
    # Pre-load common.py so network.py's import doesn't trigger __init__.
    _load_common_module()

    # Stub the WMI binding + location_paths — both load DLLs at import time,
    # which fails on non-Windows. network.py only needs get_wmi_data and
    # get_location_paths, both of which tests mock anyway.
    sys.modules.setdefault("hwprobe.interops.win.bindings.wmi", MagicMock(get_wmi_data=lambda *a, **kw: []))
    sys.modules.setdefault("hwprobe.util.location_paths", MagicMock(get_location_paths=lambda *a, **kw: None))

    mod_name = "hwprobe.core.windows.network"
    if mod_name in sys.modules:
        return sys.modules[mod_name]
    spec = importlib.util.spec_from_file_location(mod_name, _MODULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


network = _load_network_module()

# ============================================================
# Helpers
# ============================================================

def _row(name, manufacturer, pnp_device_id, adapter_type="Ethernet 802.3"):
    return {
        "Name": name,
        "Manufacturer": manufacturer,
        "PNPDeviceID": pnp_device_id,
        "AdapterType": adapter_type,
    }


def _patch_wmi(rows, monkeypatch):
    monkeypatch.setattr(network, "get_wmi_data", lambda *a, **kw: rows)


# ============================================================
# Basic parsing tests
# ============================================================


class TestBasicParsing:
    def test_successful_network_info_fetch(self, monkeypatch):
        rows = [
            _row("Intel(R) Ethernet Connection (10) I219-V", "Intel", r"PCI\VEN_8086&DEV_15B8"),
            _row("Realtek PCIe GBE Family Controller", "Realtek", r"PCI\VEN_10EC&DEV_8168"),
        ]
        _patch_wmi(rows, monkeypatch)

        network_info = network.fetch_network_info_fast()

        assert network_info.status.type == StatusType.PARTIAL
        assert len(network_info.modules) == 2
        assert network_info.modules[0].name == "Intel(R) Ethernet Connection (10) I219-V"
        assert network_info.modules[1].manufacturer == "Realtek"

    def test_empty_response_returns_failed_status(self, monkeypatch):
        _patch_wmi([], monkeypatch)

        network_info = network.fetch_network_info_fast()

        assert network_info.status.type == StatusType.FAILED
        assert len(network_info.modules) == 0
        assert any("no data" in msg for msg in network_info.status.messages)

    def test_missing_manufacturer_field(self, monkeypatch):
        rows = [_row("Intel NIC", "", r"PCI\VEN_8086&DEV_15B8")]
        _patch_wmi(rows, monkeypatch)

        network_info = network.fetch_network_info_fast()

        assert len(network_info.modules) == 0

    def test_missing_pnpdeviceid_field(self, monkeypatch):
        rows = [_row("Intel NIC", "Intel", "")]
        _patch_wmi(rows, monkeypatch)

        network_info = network.fetch_network_info_fast()

        assert len(network_info.modules) == 0


# ============================================================
# Vendor/Device ID parsing tests
# ============================================================


class TestVendorDeviceParsing:
    @pytest.mark.parametrize(
        "pnp_id,expected_vendor_id,expected_device_id",
        [
            (r"PCI\VEN_8086&DEV_15B8", "8086", "15B8"),
            (r"PCI\VEN_10EC&DEV_8168", "10EC", "8168"),
            (r"PCI\VEN_14E4&DEV_1643", "14E4", "1643"),
            (r"USB\VID_0BDA&PID_4938", "0BDA", "4938"),
            (r"USB\VID_0525&PID_A4A5", "0525", "A4A5"),
        ],
    )
    def test_parse_vendor_device_ids(self, pnp_id, expected_vendor_id, expected_device_id, monkeypatch):
        rows = [_row("Test Device", "Test", pnp_id)]
        _patch_wmi(rows, monkeypatch)

        network_info = network.fetch_network_info_fast()

        assert network_info.modules[0].vendor_id == expected_vendor_id
        assert network_info.modules[0].device_id == expected_device_id

    def test_bad_vendor_device_id_format(self, monkeypatch):
        rows = [_row("Intel NIC", "Intel", r"PCI\INVALID_FORMAT")]
        _patch_wmi(rows, monkeypatch)

        network_info = network.fetch_network_info_fast()

        assert len(network_info.modules) == 1
        assert network_info.modules[0].vendor_id is None
        assert network_info.modules[0].device_id is None
        assert network_info.status.type == StatusType.PARTIAL
        assert any("Could not parse Vendor/Device ID" in msg for msg in network_info.status.messages)


# ============================================================
# Multiple adapters and formatting tests
# ============================================================


class TestMultipleAdaptersAndFormatting:
    def test_multiple_network_adapters(self, monkeypatch):
        rows = [
            _row("Intel NIC 1", "Intel", r"PCI\VEN_8086&DEV_15B8"),
            _row("Realtek NIC", "Realtek", r"PCI\VEN_10EC&DEV_8168"),
            _row("Broadcom NIC", "Broadcom", r"PCI\VEN_14E4&DEV_1643"),
            _row("USB Adapter", "Generic", r"USB\VID_0BDA&PID_4938"),
        ]
        _patch_wmi(rows, monkeypatch)

        network_info = network.fetch_network_info_fast()

        assert len(network_info.modules) == 4
        assert network_info.modules[0].manufacturer == "Intel"
        assert network_info.modules[1].manufacturer == "Realtek"
        assert network_info.modules[2].manufacturer == "Broadcom"
        assert network_info.modules[3].manufacturer == "Generic"

    def test_whitespace_stripping(self, monkeypatch):
        rows = [_row(" Intel NIC ", " Intel ", r"PCI\VEN_8086&DEV_15B8")]
        _patch_wmi(rows, monkeypatch)

        network_info = network.fetch_network_info_fast()

        assert len(network_info.modules) == 1
        assert network_info.modules[0].manufacturer == "Intel"
        assert network_info.modules[0].name == "Intel NIC"

    def test_loopback_adapter_skipped(self, monkeypatch):
        rows = [
            _row("Loopback", "Microsoft", r"ROOT\\MS_NDISWANIP", adapter_type="Software Loopback Interface 1"),
            _row("Intel NIC", "Intel", r"PCI\VEN_8086&DEV_15B8"),
        ]
        _patch_wmi(rows, monkeypatch)

        network_info = network.fetch_network_info_fast()

        assert len(network_info.modules) == 1
        assert network_info.modules[0].name == "Intel NIC"

    def test_root_adapters_skipped(self, monkeypatch):
        rows = [
            _row("Root Device", "Microsoft", r"ROOT\\SOMETHING"),
            _row("Intel NIC", "Intel", r"PCI\VEN_8086&DEV_15B8"),
        ]
        _patch_wmi(rows, monkeypatch)

        network_info = network.fetch_network_info_fast()

        assert len(network_info.modules) == 1
        assert network_info.modules[0].name == "Intel NIC"

    def test_non_pci_usb_hardware_nic_included(self, monkeypatch):
        """NICs on non-PCI/USB buses (e.g. SDIO) should not be filtered out."""
        rows = [
            _row("Broadcom SDIO WiFi", "Broadcom", r"SD\VID_02D0&PID_A4A5"),
            _row("Intel NIC", "Intel", r"PCI\VEN_8086&DEV_15B8"),
        ]
        _patch_wmi(rows, monkeypatch)

        network_info = network.fetch_network_info_fast()

        assert len(network_info.modules) == 2
        assert network_info.modules[0].name == "Broadcom SDIO WiFi"
        assert network_info.modules[1].name == "Intel NIC"


# ============================================================
# Model structure tests
# ============================================================


class TestModelStructure:
    def test_nic_model_fields(self, monkeypatch):
        rows = [_row("Test NIC", "Intel", r"PCI\VEN_8086&DEV_15B8")]
        _patch_wmi(rows, monkeypatch)

        network_info = network.fetch_network_info_fast()
        nic = network_info.modules[0]

        assert isinstance(nic, NICInfo)
        assert nic.name == "Test NIC"
        assert nic.manufacturer == "Intel"
        assert nic.vendor_id == "8086"
        assert nic.device_id == "15B8"

    def test_network_info_model_structure(self, monkeypatch):
        rows = [_row("Test NIC", "Intel", r"PCI\VEN_8086&DEV_15B8")]
        _patch_wmi(rows, monkeypatch)

        network_info = network.fetch_network_info_fast()

        assert isinstance(network_info, NetworkInfo)
        assert hasattr(network_info, "status")
        assert hasattr(network_info, "modules")
        assert isinstance(network_info.modules, list)


class TestFunctionCallAndErrors:
    @pytest.mark.parametrize(
        "device_count,manufacturers",
        [
            (1, ["Intel"]),
            (2, ["Intel", "Realtek"]),
            (3, ["Intel", "Realtek", "Broadcom"]),
        ],
    )
    def test_various_device_counts(self, device_count, manufacturers, monkeypatch):
        rows = []
        for i, mfg in enumerate(manufacturers):
            vendor = f"VEN_{0x8086 + i:04X}" if i == 0 else f"VEN_{0x10EC + i:04X}"
            device = f"DEV_{0x15B8 + i:04X}"
            rows.append(_row(f"{mfg} NIC {i + 1}", mfg, f"PCI\\{vendor}&{device}"))
        _patch_wmi(rows, monkeypatch)

        network_info = network.fetch_network_info_fast()

        assert len(network_info.modules) == device_count
        for i, mfg in enumerate(manufacturers):
            assert network_info.modules[i].manufacturer == mfg

    def test_runtime_error_returns_failed(self, monkeypatch):
        def mock_wmi(*a, **kw):
            raise RuntimeError("get_wmi_data() failed (C library returned -1)")

        monkeypatch.setattr(network, "get_wmi_data", mock_wmi)

        network_info = network.fetch_network_info_fast()

        assert network_info.status.type == StatusType.FAILED
        assert any("-1" in msg for msg in network_info.status.messages)

    @pytest.mark.parametrize(
        "pci_path, acpi_path, exp_pci_path, exp_acpi_path",
        [
            (
                "PCIROOT(0)#PCI(1D00)#PCI(0000)#PCI(0000)#PCI(0000)",
                "ACPI(_SB_)#ACPI(PCI0)#ACPI(SAT0)#ACPI(NIC0)",
                "PciRoot(0x0)/Pci(0x1D,0x0)/Pci(0x0,0x0)/Pci(0x0,0x0)/Pci(0x0,0x0)",
                "\\_SB_.PCI0.SAT0.NIC0",
            ),
            (
                "PCIROOT(0)#PCI(1C00)#PCI(0000)#PCI(0000)#PCI(0000)",
                "ACPI(_SB_)#ACPI(PCI0)#ACPI(NIC1)",
                "PciRoot(0x0)/Pci(0x1C,0x0)/Pci(0x0,0x0)/Pci(0x0,0x0)/Pci(0x0,0x0)",
                "\\_SB_.PCI0.NIC1",
            ),
            (
                "PCIROOT(0)#PCI(1400)#PCI(0000)#PCI(0000)#PCI(0000)",
                "ACPI(_SB_)#ACPI(PCI0)#ACPI(SAT1)#ACPI(NIC2)",
                "PciRoot(0x0)/Pci(0x14,0x0)/Pci(0x0,0x0)/Pci(0x0,0x0)/Pci(0x0,0x0)",
                "\\_SB_.PCI0.SAT1.NIC2",
            ),
        ],
    )
    def test_format_paths(self, pci_path, acpi_path, exp_pci_path, exp_acpi_path, monkeypatch):
        rows = [_row("Test NIC", "Intel", r"PCI\VEN_8086&DEV_15B8")]
        _patch_wmi(rows, monkeypatch)

        def mock_get_location_paths(pnp_device_id):
            return (pci_path, acpi_path)

        monkeypatch.setattr(network, "get_location_paths", mock_get_location_paths)

        data = network.fetch_network_info_fast()
        pci, acpi = data.modules[0].pci_path, data.modules[0].acpi_path

        assert pci is not None
        assert acpi is not None
        assert pci == exp_pci_path
        assert acpi == exp_acpi_path
