import pytest

from hwprobe.core.windows import network
from hwprobe.interops.win.legacy.constants import (
    STATUS_FAILURE,
)
from hwprobe.models.network_models import NetworkInfo, NICInfo
from hwprobe.models.status_models import StatusType

# ============================================================
# Helpers
# ============================================================


# ============================================================
# Basic parsing tests
# ============================================================


class TestBasicParsing:
    """Tests for basic parsing of network device output"""

    def test_successful_network_info_fetch(self, monkeypatch):
        """Test successful retrieval and parsing of network hardware info"""
        mock_output = (
            "Manufacturer=Intel|PNPDeviceID=PCI\\VEN_8086&DEV_15B8|Name=Intel(R) Ethernet Connection (10) I219-V\n"
            "Manufacturer=Realtek|PNPDeviceID=PCI\\VEN_10EC&DEV_8168|Name=Realtek PCIe GBE Family Controller\n"
        )

        def mock_func(buf, size):
            buf.value = mock_output.encode("utf-8")
            return 0

        monkeypatch.setattr(network, "GetNetworkHardwareInfo", mock_func)

        network_info = network.fetch_network_info_fast()

        assert network_info.status.type == StatusType.PARTIAL
        assert len(network_info.modules) == 2
        assert network_info.modules[0].name == "Intel(R) Ethernet Connection (10) I219-V"
        assert network_info.modules[1].manufacturer == "Realtek"

    def test_empty_response_returns_failed_status(self, monkeypatch):
        """Test handling of empty response from GetNetworkHardwareInfo"""

        def mock_func(buf, size):
            buf.value = b""
            return 0

        monkeypatch.setattr(network, "GetNetworkHardwareInfo", mock_func)

        network_info = network.fetch_network_info_fast()

        assert network_info.status.type == StatusType.FAILED
        assert len(network_info.modules) == 0
        assert any("no data" in msg for msg in network_info.status.messages)

    def test_malformed_output_skipped(self, monkeypatch):
        """Test that malformed lines are skipped"""
        mock_output = (
            "Manufacturer=Intel|PNPDeviceID=PCI\\VEN_8086&DEV_15B8|Name=Valid NIC\n"
            "This is malformed and has no pipe separator\n"
            "Manufacturer=Realtek|PNPDeviceID=PCI\\VEN_10EC&DEV_8168|Name=Another Valid NIC\n"
        )

        def mock_func(buf, size):
            buf.value = mock_output.encode("utf-8")
            return 0

        monkeypatch.setattr(network, "GetNetworkHardwareInfo", mock_func)

        network_info = network.fetch_network_info_fast()

        assert len(network_info.modules) == 2
        assert network_info.modules[0].name == "Valid NIC"
        assert network_info.modules[1].name == "Another Valid NIC"

    def test_bad_vendor_device_id_format(self, monkeypatch):
        """Test handling of bad Vendor/Device ID format in PNPDeviceID"""
        mock_output = "Manufacturer=Intel|PNPDeviceID=PCI\\INVALID_FORMAT|Name=Intel NIC\n"

        def mock_func(buf, size):
            buf.value = mock_output.encode("utf-8")
            return 0

        monkeypatch.setattr(network, "GetNetworkHardwareInfo", mock_func)

        network_info = network.fetch_network_info_fast()

        assert len(network_info.modules) == 1
        assert network_info.modules[0].vendor_id is None
        assert network_info.modules[0].device_id is None
        assert network_info.status.type == StatusType.PARTIAL
        assert any("Could not parse Vendor/Device ID" in msg for msg in network_info.status.messages)

    def test_missing_manufacturer_field(self, monkeypatch):
        """Test handling of missing Manufacturer field"""
        mock_output = "PNPDeviceID=PCI\\VEN_8086&DEV_15B8|Name=Intel NIC\n"

        def mock_func(buf, size):
            buf.value = mock_output.encode("utf-8")
            return 0

        monkeypatch.setattr(network, "GetNetworkHardwareInfo", mock_func)

        network_info = network.fetch_network_info_fast()

        assert len(network_info.modules) == 0

    def test_missing_pnpdeviceid_field(self, monkeypatch):
        """Test handling of missing PNPDeviceID field"""
        mock_output = "Manufacturer=Intel|Name=Intel NIC\n"

        def mock_func(buf, size):
            buf.value = mock_output.encode("utf-8")
            return 0

        monkeypatch.setattr(network, "GetNetworkHardwareInfo", mock_func)

        network_info = network.fetch_network_info_fast()

        assert len(network_info.modules) == 0


# ============================================================
# Vendor/Device ID parsing tests
# ============================================================


class TestVendorDeviceParsing:
    """Tests for vendor and device ID parsing"""

    @pytest.mark.parametrize(
        "pnp_id,expected_vendor_id,expected_device_id",
        [
            ("PCI\\VEN_8086&DEV_15B8", "8086", "15B8"),
            ("PCI\\VEN_10EC&DEV_8168", "10EC", "8168"),
            ("PCI\\VEN_14E4&DEV_1643", "14E4", "1643"),
            ("USB\\VID_0BDA&PID_4938", "0BDA", "4938"),
            ("USB\\VID_0525&PID_A4A5", "0525", "A4A5"),
        ],
    )
    def test_parse_vendor_device_ids(self, pnp_id, expected_vendor_id, expected_device_id, monkeypatch):
        """Test parsing various vendor/device ID combinations"""
        mock_output = f"Manufacturer=Test|PNPDeviceID={pnp_id}|Name=Test Device\n"

        def mock_func(buf, size):
            buf.value = mock_output.encode("utf-8")
            return 0

        monkeypatch.setattr(network, "GetNetworkHardwareInfo", mock_func)

        network_info = network.fetch_network_info_fast()

        assert network_info.modules[0].vendor_id == expected_vendor_id
        assert network_info.modules[0].device_id == expected_device_id


# ============================================================
# Multiple adapters and formatting tests
# ============================================================


class TestMultipleAdaptersAndFormatting:
    """Tests for multiple adapters and output formatting"""

    def test_multiple_network_adapters(self, monkeypatch):
        """Test parsing multiple network adapters"""
        mock_output = (
            "Manufacturer=Intel|PNPDeviceID=PCI\\VEN_8086&DEV_15B8|Name=Intel NIC 1\n"
            "Manufacturer=Realtek|PNPDeviceID=PCI\\VEN_10EC&DEV_8168|Name=Realtek NIC\n"
            "Manufacturer=Broadcom|PNPDeviceID=PCI\\VEN_14E4&DEV_1643|Name=Broadcom NIC\n"
            "Manufacturer=Generic|PNPDeviceID=USB\\VID_0BDA&PID_4938|Name=USB Adapter\n"
        )

        def mock_func(buf, size):
            buf.value = mock_output.encode("utf-8")
            return 0

        monkeypatch.setattr(network, "GetNetworkHardwareInfo", mock_func)

        network_info = network.fetch_network_info_fast()

        assert len(network_info.modules) == 4
        assert network_info.modules[0].manufacturer == "Intel"
        assert network_info.modules[1].manufacturer == "Realtek"
        assert network_info.modules[2].manufacturer == "Broadcom"
        assert network_info.modules[3].manufacturer == "Generic"

    def test_whitespace_stripping(self, monkeypatch):
        """Test that whitespace is properly stripped from fields"""
        mock_output = "Manufacturer= Intel |PNPDeviceID= PCI\\VEN_8086&DEV_15B8 |Name= Intel NIC \n"

        def mock_func(buf, size):
            buf.value = mock_output.encode("utf-8")
            return 0

        monkeypatch.setattr(network, "GetNetworkHardwareInfo", mock_func)

        network_info = network.fetch_network_info_fast()

        assert len(network_info.modules) == 1
        # Whitespace should be stripped
        assert network_info.modules[0].manufacturer == "Intel"
        assert network_info.modules[0].name == "Intel NIC"

    def test_blank_lines_ignored(self, monkeypatch):
        """Test that blank lines are properly ignored"""
        mock_output = (
            "Manufacturer=Intel|PNPDeviceID=PCI\\VEN_8086&DEV_15B8|Name=Intel NIC\n"
            "\n"
            "\n"
            "Manufacturer=Realtek|PNPDeviceID=PCI\\VEN_10EC&DEV_8168|Name=Realtek NIC\n"
        )

        def mock_func(buf, size):
            buf.value = mock_output.encode("utf-8")
            return 0

        monkeypatch.setattr(network, "GetNetworkHardwareInfo", mock_func)

        network_info = network.fetch_network_info_fast()

        assert len(network_info.modules) == 2


# ============================================================
# Model structure tests
# ============================================================


class TestModelStructure:
    """Tests for data model structure and fields"""

    def test_nic_model_fields(self, monkeypatch):
        """Test that NICInfo model fields are correctly populated"""
        mock_output = "Manufacturer=Intel|PNPDeviceID=PCI\\VEN_8086&DEV_15B8|Name=Test NIC\n"

        def mock_func(buf, size):
            buf.value = mock_output.encode("utf-8")
            return 0

        monkeypatch.setattr(network, "GetNetworkHardwareInfo", mock_func)

        network_info = network.fetch_network_info_fast()
        nic = network_info.modules[0]

        assert isinstance(nic, NICInfo)
        assert nic.name == "Test NIC"
        assert nic.manufacturer == "Intel"
        assert nic.vendor_id == "8086"
        assert nic.device_id == "15B8"

    def test_network_info_model_structure(self, monkeypatch):
        """Test that NetworkInfo model has correct structure"""
        mock_output = "Manufacturer=Intel|PNPDeviceID=PCI\\VEN_8086&DEV_15B8|Name=Test NIC\n"

        def mock_func(buf, size):
            buf.value = mock_output.encode("utf-8")
            return 0

        monkeypatch.setattr(network, "GetNetworkHardwareInfo", mock_func)

        network_info = network.fetch_network_info_fast()

        assert isinstance(network_info, NetworkInfo)
        assert hasattr(network_info, "status")
        assert hasattr(network_info, "modules")
        assert isinstance(network_info.modules, list)


class TestFunctionCallAndErrors:
    """Tests for function behavior and error conditions"""

    def test_function_call(self, monkeypatch):
        """Test that GetNetworkHardwareInfo is called successfully"""

        def mock_func(buf, size):
            buf.value = b""
            return 0

        monkeypatch.setattr(network, "GetNetworkHardwareInfo", mock_func)

        network.fetch_network_info_fast()

    @pytest.mark.parametrize(
        "device_count,manufacturers",
        [
            (1, ["Intel"]),
            (2, ["Intel", "Realtek"]),
            (3, ["Intel", "Realtek", "Broadcom"]),
        ],
    )
    def test_various_device_counts(self, device_count, manufacturers, monkeypatch):
        """Test parsing various numbers of network devices"""
        lines = []
        for i, mfg in enumerate(manufacturers):
            vendor = f"VEN_{0x8086 + i:04X}" if i == 0 else f"VEN_{0x10EC + i:04X}"
            device = f"DEV_{0x15B8 + i:04X}"
            lines.append(f"Manufacturer={mfg}|PNPDeviceID=PCI\\{vendor}&{device}|Name={mfg} NIC {i + 1}")
        mock_output = "\n".join(lines) + "\n"

        def mock_func(buf, size):
            buf.value = mock_output.encode("utf-8")
            return 0

        monkeypatch.setattr(network, "GetNetworkHardwareInfo", mock_func)

        network_info = network.fetch_network_info_fast()

        assert len(network_info.modules) == device_count
        for i, mfg in enumerate(manufacturers):
            assert network_info.modules[i].manufacturer == mfg

    def test_multiple_network_adapters(self, monkeypatch):
        """Test parsing multiple network adapters"""
        mock_output = (
            "Manufacturer=Intel|PNPDeviceID=PCI\\VEN_8086&DEV_15B8|Name=Intel NIC 1\n"
            "Manufacturer=Realtek|PNPDeviceID=PCI\\VEN_10EC&DEV_8168|Name=Realtek NIC\n"
            "Manufacturer=Broadcom|PNPDeviceID=PCI\\VEN_14E4&DEV_1643|Name=Broadcom NIC\n"
            "Manufacturer=Generic|PNPDeviceID=USB\\VID_0BDA&PID_4938|Name=USB Adapter\n"
        )

        def mock_func(buf, size):
            buf.value = mock_output.encode("utf-8")
            return 0

        monkeypatch.setattr(network, "GetNetworkHardwareInfo", mock_func)

        network_info = network.fetch_network_info_fast()

        assert len(network_info.modules) == 4
        assert network_info.modules[0].manufacturer == "Intel"
        assert network_info.modules[1].manufacturer == "Realtek"
        assert network_info.modules[2].manufacturer == "Broadcom"
        assert network_info.modules[3].manufacturer == "Generic"

    def test_function_call_with_bad_status(self, monkeypatch):
        """Test handling of non-OK status from GetNetworkHardwareInfo"""

        def mock_func(buf, size):
            buf.value = b""
            return STATUS_FAILURE

        monkeypatch.setattr(network, "GetNetworkHardwareInfo", mock_func)

        network_info = network.fetch_network_info_fast()

        assert network_info.status.type == StatusType.FAILED
        assert any("status code:" in msg for msg in network_info.status.messages)

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
        """Test that format_{pci|acpi}_path returns correct PCI and ACPI path"""

        def mock_get_location_paths(pnp_device_id):
            return (
                pci_path,
                acpi_path,
            )

        monkeypatch.setattr(network, "get_location_paths", mock_get_location_paths)

        data = network.fetch_network_info_fast()
        pci, acpi = data.modules[0].pci_path, data.modules[0].acpi_path

        assert pci is not None
        assert acpi is not None
        assert pci == exp_pci_path
        assert acpi == exp_acpi_path
