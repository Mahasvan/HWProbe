from dataclasses import dataclass
from unittest.mock import MagicMock, patch

from hwprobe.core.mac.storage import fetch_storage_info
from hwprobe.models.status_models import StatusType

# ── lightweight stand-in for the binding's dataclass ─────────────────────────


@dataclass
class FakeStorageDeviceProperties:
    product_name: str
    vendor_name: str
    medium_type: str
    interconnect: str
    location: str
    bsd_name: str
    size_bytes: int


# ── helpers ──────────────────────────────────────────────────────────────────


def _nvme_ssd(
    product_name="APPLE SSD AP0512Z",
    vendor_name="",
    medium_type="Solid State",
    interconnect="PCI-Express",
    location="Internal",
    bsd_name="disk0",
    size_bytes=500_107_862_016,
) -> FakeStorageDeviceProperties:
    return FakeStorageDeviceProperties(
        product_name=product_name,
        vendor_name=vendor_name,
        medium_type=medium_type,
        interconnect=interconnect,
        location=location,
        bsd_name=bsd_name,
        size_bytes=size_bytes,
    )


def _sata_ssd(
    product_name="Samsung SSD 860 EVO 1TB",
    vendor_name="Samsung",
    medium_type="Solid State",
    interconnect="SATA",
    location="Internal",
    bsd_name="disk1",
    size_bytes=1_000_204_886_016,
) -> FakeStorageDeviceProperties:
    return FakeStorageDeviceProperties(
        product_name=product_name,
        vendor_name=vendor_name,
        medium_type=medium_type,
        interconnect=interconnect,
        location=location,
        bsd_name=bsd_name,
        size_bytes=size_bytes,
    )


def _hdd(
    product_name="WDC WD10EZEX-00W",
    vendor_name="Western Digital",
    medium_type="Rotational",
    interconnect="SATA",
    location="Internal",
    bsd_name="disk2",
    size_bytes=1_000_204_886_016,
) -> FakeStorageDeviceProperties:
    return FakeStorageDeviceProperties(
        product_name=product_name,
        vendor_name=vendor_name,
        medium_type=medium_type,
        interconnect=interconnect,
        location=location,
        bsd_name=bsd_name,
        size_bytes=size_bytes,
    )


def _usb_drive(
    product_name="SanDisk Ultra",
    vendor_name="SanDisk",
    medium_type="",
    interconnect="USB",
    location="External",
    bsd_name="disk3",
    size_bytes=32_015_982_592,
) -> FakeStorageDeviceProperties:
    return FakeStorageDeviceProperties(
        product_name=product_name,
        vendor_name=vendor_name,
        medium_type=medium_type,
        interconnect=interconnect,
        location=location,
        bsd_name=bsd_name,
        size_bytes=size_bytes,
    )


def _apple_fabric_ssd(
    product_name="APPLE SSD AP0512Z",
    vendor_name="",
    medium_type="Solid State",
    interconnect="Apple Fabric",
    location="Internal",
    bsd_name="disk0",
    size_bytes=500_107_862_016,
) -> FakeStorageDeviceProperties:
    return FakeStorageDeviceProperties(
        product_name=product_name,
        vendor_name=vendor_name,
        medium_type=medium_type,
        interconnect=interconnect,
        location=location,
        bsd_name=bsd_name,
        size_bytes=size_bytes,
    )


def _patch_binding(disk_list):
    """
    Return a context-manager that patches the lazy import inside
    fetch_storage_info so that get_storage_info() returns *disk_list*.
    """
    mock_module = MagicMock()
    mock_module.get_storage_info.return_value = disk_list
    mock_module.StorageDeviceProperties = FakeStorageDeviceProperties

    return patch.dict(
        "sys.modules",
        {"hwprobe.interops.mac.bindings.storage_info": mock_module},
    )


def _run(disk_list):
    import sys

    sys.modules.pop("hwprobe.interops.mac.bindings.storage_info", None)
    with _patch_binding(disk_list):
        return fetch_storage_info()


# ── dylib / binding load failures ────────────────────────────────────────────


class TestBindingLoadFailures:
    """fetch_storage_info must gracefully handle errors that arise when the
    C binding cannot be imported or when IOKit enumeration fails."""

    def test_dylib_not_found_returns_failed_status(self):
        """FileNotFoundError raised at module import time -> FAILED with a rebuild hint."""
        import importlib.abc
        import sys

        _TARGET = "hwprobe.interops.mac.bindings.storage_info"

        class _DylibMissingFinder(importlib.abc.MetaPathFinder):
            def find_spec(self, fullname, path, target=None):
                if fullname == _TARGET:
                    raise FileNotFoundError(
                        "libdevice_info.dylib not found at .../bindings/libdevice_info.dylib.\n"
                        "Build the project first:  cmake --build cmake-build-debug"
                    )

        finder = _DylibMissingFinder()
        sys.meta_path.insert(0, finder)
        sys.modules.pop(_TARGET, None)
        try:
            info = fetch_storage_info()
        finally:
            sys.meta_path.remove(finder)
            sys.modules.pop(_TARGET, None)

        assert info.status.type == StatusType.FAILED
        assert any("libdevice_info.dylib" in m or "rebuild" in m.lower() for m in info.status.messages)
        assert info.modules == []

    def test_iokit_enumeration_failure_returns_failed_status(self):
        """RuntimeError (get_storage_info returns -1) -> FAILED."""
        mock_module = MagicMock()
        mock_module.get_storage_info.side_effect = RuntimeError("get_storage_info() failed (C library returned -1)")

        import sys

        sys.modules.pop("hwprobe.interops.mac.bindings.storage_info", None)

        with patch.dict("sys.modules", {"hwprobe.interops.mac.bindings.storage_info": mock_module}):
            info = fetch_storage_info()

        assert info.status.type == StatusType.FAILED
        assert any("IOKit" in m or "-1" in m for m in info.status.messages)
        assert info.modules == []

    def test_unexpected_exception_returns_failed_status(self):
        """Any other exception during binding load -> FAILED."""
        mock_module = MagicMock()
        mock_module.get_storage_info.side_effect = OSError("Unexpected OS error")

        import sys

        sys.modules.pop("hwprobe.interops.mac.bindings.storage_info", None)

        with patch.dict("sys.modules", {"hwprobe.interops.mac.bindings.storage_info": mock_module}):
            info = fetch_storage_info()

        assert info.status.type == StatusType.FAILED
        assert len(info.status.messages) == 1
        assert info.modules == []


# ── NVMe SSD (happy path) ────────────────────────────────────────────────────


class TestNVMeSSD:
    """Tests covering NVMe SSD enumeration via PCI-Express interconnect."""

    def test_nvme_ssd_type_is_nvme(self):
        info = _run([_nvme_ssd()])
        assert info.status.type == StatusType.SUCCESS
        assert len(info.modules) == 1

        disk = info.modules[0]
        assert disk.type == "Non-Volatile Memory Express (NVMe)"

    def test_nvme_ssd_model_name(self):
        info = _run([_nvme_ssd(product_name="APPLE SSD AP1024Z")])
        assert info.modules[0].model == "APPLE SSD AP1024Z"

    def test_nvme_ssd_location_internal(self):
        info = _run([_nvme_ssd(location="Internal")])
        assert info.modules[0].location == "Internal"

    def test_nvme_ssd_connector_is_pci_express(self):
        info = _run([_nvme_ssd(interconnect="PCI-Express")])
        assert info.modules[0].connector == "PCI-Express"

    def test_nvme_ssd_size_converted_to_megabytes(self):
        info = _run([_nvme_ssd(size_bytes=500_107_862_016)])
        disk = info.modules[0]
        assert disk.size is not None
        assert disk.size.capacity == 500_107_862_016 // (1024 * 1024)
        assert disk.size.unit == "MB"

    def test_nvme_overrides_medium_type(self):
        """PCI-Express interconnect should produce NVMe type regardless of medium_type value."""
        info = _run([_nvme_ssd(medium_type="Rotational")])
        assert info.modules[0].type == "Non-Volatile Memory Express (NVMe)"

    def test_nvme_pci_express_case_insensitive(self):
        """PCI-Express check should be case-insensitive."""
        info = _run([_nvme_ssd(interconnect="pci-express")])
        assert info.modules[0].type == "Non-Volatile Memory Express (NVMe)"


# ── Apple Fabric SSD ─────────────────────────────────────────────────────────


class TestAppleFabricSSD:
    """Tests for Apple Silicon Macs using Apple Fabric interconnect."""

    def test_apple_fabric_ssd_type_is_ssd(self):
        info = _run([_apple_fabric_ssd()])
        assert info.status.type == StatusType.SUCCESS
        disk = info.modules[0]
        assert disk.type == "Solid State Drive (SSD)"
        assert disk.connector == "Apple Fabric"

    def test_apple_fabric_ssd_manufacturer_inferred(self):
        """Vendor name is empty, but product name contains 'Apple' -> manufacturer is 'Apple'."""
        info = _run([_apple_fabric_ssd(vendor_name="", product_name="APPLE SSD AP0512Z")])
        assert info.modules[0].manufacturer == "Apple"

    def test_apple_fabric_ssd_vendor_name_takes_priority(self):
        """If vendor_name is provided, it takes priority over name inference."""
        info = _run([_apple_fabric_ssd(vendor_name="Apple Inc.")])
        assert info.modules[0].manufacturer == "Apple Inc."


# ── SATA SSD ─────────────────────────────────────────────────────────────────


class TestSATASSD:
    """Tests for SATA-connected SSDs."""

    def test_sata_ssd_type_is_ssd(self):
        info = _run([_sata_ssd()])
        assert info.status.type == StatusType.SUCCESS
        disk = info.modules[0]
        assert disk.type == "Solid State Drive (SSD)"

    def test_sata_ssd_manufacturer(self):
        info = _run([_sata_ssd(vendor_name="Samsung")])
        assert info.modules[0].manufacturer == "Samsung"

    def test_sata_ssd_connector(self):
        info = _run([_sata_ssd()])
        assert info.modules[0].connector == "SATA"

    def test_sata_ssd_size(self):
        info = _run([_sata_ssd(size_bytes=1_000_204_886_016)])
        disk = info.modules[0]
        assert disk.size is not None
        assert disk.size.capacity == 1_000_204_886_016 // (1024 * 1024)


# ── HDD ──────────────────────────────────────────────────────────────────────


class TestHDD:
    """Tests for rotational hard disk drives."""

    def test_hdd_type_is_hdd(self):
        info = _run([_hdd()])
        assert info.status.type == StatusType.SUCCESS
        assert info.modules[0].type == "Hard Disk Drive (HDD)"

    def test_hdd_manufacturer(self):
        info = _run([_hdd(vendor_name="Western Digital")])
        assert info.modules[0].manufacturer == "Western Digital"


# ── USB / External Drives ────────────────────────────────────────────────────


class TestExternalDrive:
    """Tests for USB and other external drives."""

    def test_usb_drive_location_external(self):
        info = _run([_usb_drive()])
        assert info.status.type == StatusType.SUCCESS
        disk = info.modules[0]
        assert disk.location == "External"
        assert disk.connector == "USB"

    def test_usb_drive_unknown_medium_type(self):
        """Empty medium_type (no medium_type from IOKit) -> 'Unknown'."""
        info = _run([_usb_drive(medium_type="")])
        assert info.modules[0].type == "Unknown"

    def test_usb_drive_size(self):
        info = _run([_usb_drive(size_bytes=32_015_982_592)])
        assert info.modules[0].size.capacity == 32_015_982_592 // (1024 * 1024)


# ── Multiple Disks ───────────────────────────────────────────────────────────


class TestMultipleDisks:
    """Tests for machines with more than one storage device."""

    def test_two_disks_enumerated(self):
        info = _run([_nvme_ssd(), _hdd()])
        assert info.status.type == StatusType.SUCCESS
        assert len(info.modules) == 2

    def test_multiple_disk_types_correct(self):
        info = _run(
            [
                _nvme_ssd(product_name="NVMe Drive"),
                _sata_ssd(product_name="SATA SSD"),
                _hdd(product_name="Big HDD"),
            ]
        )
        assert len(info.modules) == 3
        assert info.modules[0].type == "Non-Volatile Memory Express (NVMe)"
        assert info.modules[1].type == "Solid State Drive (SSD)"
        assert info.modules[2].type == "Hard Disk Drive (HDD)"

    def test_internal_and_external_mixed(self):
        info = _run(
            [
                _apple_fabric_ssd(location="Internal"),
                _usb_drive(location="External"),
            ]
        )
        assert len(info.modules) == 2
        assert info.modules[0].location == "Internal"
        assert info.modules[1].location == "External"


# ── Edge Cases ───────────────────────────────────────────────────────────────


class TestEdgeCases:
    """Misc edge-case and boundary tests."""

    def test_empty_disk_list_returns_success(self):
        info = _run([])
        assert info.status.type == StatusType.SUCCESS
        assert info.modules == []

    def test_empty_product_name_sets_model_none(self):
        info = _run([_nvme_ssd(product_name="")])
        assert info.modules[0].model is None

    def test_whitespace_only_product_name_sets_model_none(self):
        info = _run([_nvme_ssd(product_name="   ")])
        assert info.modules[0].model is None

    def test_empty_vendor_name_no_apple_in_name(self):
        """No vendor name and no 'apple' in product name -> manufacturer is None."""
        info = _run([_sata_ssd(vendor_name="", product_name="Samsung SSD 860")])
        assert info.modules[0].manufacturer is None

    def test_empty_vendor_name_apple_in_name(self):
        """No vendor name but 'apple' in product name -> manufacturer is 'Apple'."""
        info = _run([_nvme_ssd(vendor_name="", product_name="APPLE SSD AP0512Z")])
        assert info.modules[0].manufacturer == "Apple"

    def test_empty_interconnect_sets_connector_none(self):
        info = _run([_nvme_ssd(interconnect="")])
        assert info.modules[0].connector is None

    def test_empty_location_defaults_to_unknown(self):
        info = _run([_nvme_ssd(location="")])
        assert info.modules[0].location == "Unknown"

    def test_zero_size_bytes_sets_size_none(self):
        info = _run([_nvme_ssd(size_bytes=0)])
        assert info.modules[0].size is None

    def test_unknown_medium_type_passed_through(self):
        """Medium types not in STORAGE_MAP are passed through verbatim."""
        info = _run([_nvme_ssd(medium_type="Optical", interconnect="SATA")])
        assert info.modules[0].type == "Optical"

    def test_whitespace_in_vendor_name_is_trimmed(self):
        info = _run([_sata_ssd(vendor_name="  Samsung  ")])
        assert info.modules[0].manufacturer == "Samsung"

    def test_whitespace_in_product_name_is_trimmed(self):
        info = _run([_sata_ssd(product_name="  Samsung SSD 860  ")])
        assert info.modules[0].model == "Samsung SSD 860"

    def test_large_disk_size(self):
        """8 TB disk."""
        size_8tb = 8 * 1024 * 1024 * 1024 * 1024
        info = _run([_hdd(size_bytes=size_8tb)])
        assert info.modules[0].size.capacity == size_8tb // (1024 * 1024)

    def test_return_type_is_storage_info(self):
        from hwprobe.models.storage_models import StorageInfo

        info = _run([_nvme_ssd()])
        assert isinstance(info, StorageInfo)

    def test_size_unit_is_megabytes(self):
        info = _run([_nvme_ssd(size_bytes=500_107_862_016)])
        assert info.modules[0].size.unit == "MB"

    def test_sd_card_reader_no_size(self):
        """SD card readers with no media inserted report 0 bytes."""
        reader = FakeStorageDeviceProperties(
            product_name="Built In SDXC Reader",
            vendor_name="Apple",
            medium_type="",
            interconnect="Secure Digital",
            location="Internal",
            bsd_name="disk4",
            size_bytes=0,
        )
        info = _run([reader])
        assert info.status.type == StatusType.SUCCESS
        disk = info.modules[0]
        assert disk.model == "Built In SDXC Reader"
        assert disk.manufacturer == "Apple"
        assert disk.connector == "Secure Digital"
        assert disk.size is None
