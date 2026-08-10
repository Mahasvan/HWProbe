import builtins
import os
import posixpath
from unittest.mock import MagicMock

from hwprobe.core.linux.storage import fetch_storage_info
from hwprobe.models.status_models import StatusType


class TestLinuxStorage:
    def test_fetch_storage_info_no_sys_block(self, monkeypatch):
        monkeypatch.setattr(posixpath, "isdir", lambda x: False)

        storage_info = fetch_storage_info()

        assert storage_info.status.type == StatusType.FAILED
        assert "does not exist" in storage_info.status.messages[0]

    def test_fetch_storage_info_nvme_success(self, monkeypatch):
        monkeypatch.setattr(posixpath, "isdir", lambda x: True)
        monkeypatch.setattr(posixpath, "exists", lambda x: False)
        monkeypatch.setattr(os, "listdir", lambda x: ["nvme0n1", "loop0"])

        def mock_open(path, mode="r"):
            mock_file = MagicMock()
            content = ""
            if "nvme0n1/device/model" in path:
                content = "Samsung SSD 970 EVO Plus 1TB"
            elif "nvme0n1/queue/rotational" in path or "nvme0n1/removable" in path:
                content = "0"
            elif "nvme0n1/device/device/device" in path:
                content = "0xa808"
            elif "nvme0n1/device/device/vendor" in path:
                content = "0x144d"
            elif "nvme0n1/size" in path:
                content = "1953525168"  # 1TB in 512-byte blocks

            mock_file.read.return_value = content
            mock_file.__enter__.return_value = mock_file
            return mock_file

        monkeypatch.setattr(builtins, "open", mock_open)

        storage_info = fetch_storage_info()

        assert storage_info.status.type == StatusType.SUCCESS
        assert len(storage_info.modules) == 1
        disk = storage_info.modules[0]
        assert disk.model == "Samsung SSD 970 EVO Plus 1TB"
        assert disk.type == "Non-Volatile Memory Express (NVMe)"
        assert disk.location == "Internal"
        assert disk.connector == "PCIe"
        assert disk.vendor_id == "0x144d"
        assert disk.device_id == "0xa808"
        # 1953525168 * 512 / 1024 / 1024 = 953869.7109375 MB -> 953869 MB
        assert disk.size is not None
        assert disk.size.capacity == 953869

    def test_fetch_storage_info_sd_success(self, monkeypatch):
        monkeypatch.setattr(posixpath, "isdir", lambda x: True)
        monkeypatch.setattr(posixpath, "exists", lambda x: False)
        monkeypatch.setattr(os, "listdir", lambda x: ["sda"])

        def mock_open(path, mode="r"):
            mock_file = MagicMock()
            content = ""
            if "sda/device/model" in path:
                content = "WDC WD10EZEX-08W"
            elif "sda/queue/rotational" in path:
                content = "1"
            elif "sda/removable" in path:
                content = "0"
            elif "sda/device/vendor" in path:
                content = "ATA"
            elif "sda/size" in path:
                content = "1953525168"

            mock_file.read.return_value = content
            mock_file.__enter__.return_value = mock_file
            return mock_file

        monkeypatch.setattr(builtins, "open", mock_open)

        storage_info = fetch_storage_info()

        assert storage_info.status.type == StatusType.SUCCESS
        assert len(storage_info.modules) == 1
        disk = storage_info.modules[0]
        assert disk.model == "WDC WD10EZEX-08W"
        assert disk.type == "Hard Disk Drive (HDD)"
        assert disk.location == "Internal"
        assert disk.connector == "SCSI"
        assert disk.vendor_id == "ATA"
        assert disk.size is not None
        assert disk.size.capacity == 953869

    def test_fetch_storage_info_partial_failure(self, monkeypatch):
        monkeypatch.setattr(posixpath, "isdir", lambda x: True)
        monkeypatch.setattr(posixpath, "exists", lambda x: False)
        monkeypatch.setattr(os, "listdir", lambda x: ["sda"])

        def mock_open(path, mode="r"):
            mock_file = MagicMock()
            content = ""
            if "sda/device/model" in path:
                content = ""  # Empty model
            elif "sda/queue/rotational" in path:
                content = "1"
            elif "sda/removable" in path:
                content = "0"
            elif "sda/device/vendor" in path:
                content = "ATA"
            elif "sda/size" in path:
                content = "1000"

            mock_file.read.return_value = content
            mock_file.__enter__.return_value = mock_file
            return mock_file

        monkeypatch.setattr(builtins, "open", mock_open)

        storage_info = fetch_storage_info()

        assert storage_info.status.type == StatusType.PARTIAL
        assert "Disk Model could not be found" in storage_info.status.messages
        assert len(storage_info.modules) == 1

    def test_fetch_storage_info_exception(self, monkeypatch):
        monkeypatch.setattr(posixpath, "isdir", lambda x: True)
        monkeypatch.setattr(posixpath, "exists", lambda x: False)
        monkeypatch.setattr(os, "listdir", lambda x: ["sda"])

        def mock_open(path, mode="r"):
            raise PermissionError("Access denied")

        monkeypatch.setattr(builtins, "open", mock_open)

        storage_info = fetch_storage_info()

        assert storage_info.status.type == StatusType.PARTIAL
        assert any("Disk Info (sda): Access denied" in msg for msg in storage_info.status.messages)
        assert len(storage_info.modules) == 0

    def test_fetch_storage_info_emmc_success(self, monkeypatch):
        monkeypatch.setattr(posixpath, "isdir", lambda x: True)
        monkeypatch.setattr(posixpath, "exists", lambda x: False)
        monkeypatch.setattr(os, "listdir", lambda x: ["mmcblk0"])

        def mock_open(path, mode="r"):
            mock_file = MagicMock()
            content = ""
            if "mmcblk0/device/name" in path:
                content = "BJTD4R"
            elif "mmcblk0/removable" in path:
                content = "0"
            elif "mmcblk0/device/manfid" in path:
                content = "0x000015"
            elif "mmcblk0/device/oemid" in path:
                content = "0x0100"
            elif "mmcblk0/size" in path:
                content = "62537728"  # 32GB in 512-byte blocks

            mock_file.read.return_value = content
            mock_file.__enter__.return_value = mock_file
            return mock_file

        monkeypatch.setattr(builtins, "open", mock_open)

        storage_info = fetch_storage_info()

        assert storage_info.status.type == StatusType.SUCCESS
        assert len(storage_info.modules) == 1
        disk = storage_info.modules[0]
        assert disk.identifier == "mmcblk0"
        assert disk.model == "BJTD4R"
        assert disk.type == "Embedded MultiMediaCard (eMMC)"
        assert disk.location == "Internal"
        assert disk.connector == "Unknown"
        assert disk.vendor_id == "0x000015"
        assert disk.device_id == "0x0100"
        assert disk.size is not None
        assert disk.size.capacity == 30536

    def test_fetch_storage_info_sd_card_success(self, monkeypatch):
        monkeypatch.setattr(posixpath, "isdir", lambda x: True)
        monkeypatch.setattr(posixpath, "exists", lambda x: False)
        monkeypatch.setattr(os, "listdir", lambda x: ["mmcblk1"])

        def mock_open(path, mode="r"):
            mock_file = MagicMock()
            content = ""
            if "mmcblk1/device/name" in path:
                content = "SD64G"
            elif "mmcblk1/removable" in path:
                content = "1"
            elif "mmcblk1/device/manfid" in path:
                content = "0x000003"
            elif "mmcblk1/device/oemid" in path:
                content = "0x5344"
            elif "mmcblk1/size" in path:
                content = "125829120"  # 64GB in 512-byte blocks

            mock_file.read.return_value = content
            mock_file.__enter__.return_value = mock_file
            return mock_file

        monkeypatch.setattr(builtins, "open", mock_open)

        storage_info = fetch_storage_info()

        assert storage_info.status.type == StatusType.SUCCESS
        assert len(storage_info.modules) == 1
        disk = storage_info.modules[0]
        assert disk.identifier == "mmcblk1"
        assert disk.model == "SD64G"
        assert disk.type == "Secure Digital (SD)"
        assert disk.location == "External"
        assert disk.connector == "Unknown"
        assert disk.vendor_id == "0x000003"
        assert disk.device_id == "0x5344"
        assert disk.size is not None
        assert disk.size.capacity == 61440

    def test_fetch_storage_info_emmc_partial_failure(self, monkeypatch):
        monkeypatch.setattr(posixpath, "isdir", lambda x: True)
        monkeypatch.setattr(posixpath, "exists", lambda x: False)
        monkeypatch.setattr(os, "listdir", lambda x: ["mmcblk0"])

        def mock_open(path, mode="r"):
            mock_file = MagicMock()
            content = ""
            if "mmcblk0/device/name" in path:
                content = ""  # Empty model
            elif "mmcblk0/removable" in path:
                content = "0"
            elif "mmcblk0/device/manfid" in path:
                content = ""  # Empty vendor ID
            elif "mmcblk0/device/oemid" in path:
                content = ""  # Empty device ID
            elif "mmcblk0/size" in path:
                content = "62537728"

            mock_file.read.return_value = content
            mock_file.__enter__.return_value = mock_file
            return mock_file

        monkeypatch.setattr(builtins, "open", mock_open)

        storage_info = fetch_storage_info()

        assert storage_info.status.type == StatusType.PARTIAL
        assert "Disk Model could not be found" in storage_info.status.messages
        assert "Disk vendor id could not be found" in storage_info.status.messages
        assert "Disk device id could not be found" in storage_info.status.messages
        assert len(storage_info.modules) == 1

    def test_fetch_storage_info_filters_partitions_and_boot_devices(self, monkeypatch):
        monkeypatch.setattr(posixpath, "isdir", lambda x: True)
        monkeypatch.setattr(
            os,
            "listdir",
            lambda x: [
                "sda",
                "sda1",
                "sda2",  # sda is disk, sda1/sda2 are partitions
                "mmcblk0",
                "mmcblk0p1",
                "mmcblk0boot0",
                "mmcblk0boot1",
                "mmcblk0rpmb",
                # mmcblk0 is disk, others should be filtered
                "nvme0n1",
                "nvme0n1p1",
                "nvme0n1p2",  # nvme0n1 is disk, partitions should be filtered
            ],
        )

        def mock_exists(path):
            # Only partition files exist for actual partitions
            return (
                "sda1/partition" in path
                or "sda2/partition" in path
                or "mmcblk0p1/partition" in path
                or "nvme0n1p1/partition" in path
                or "nvme0n1p2/partition" in path
            )

        monkeypatch.setattr(posixpath, "exists", mock_exists)

        def mock_open(path, mode="r"):
            mock_file = MagicMock()
            content = ""

            # Mock for sda
            if "sda/device/model" in path:
                content = "Test SSD"
            elif "sda/queue/rotational" in path or "sda/removable" in path:
                content = "0"
            elif "sda/device/vendor" in path:
                content = "TestVendor"
            elif "sda/size" in path:
                content = "1000000"

            # Mock for mmcblk0
            elif "mmcblk0/device/name" in path:
                content = "TesteMMC"
            elif "mmcblk0/removable" in path:
                content = "0"
            elif "mmcblk0/device/manfid" in path:
                content = "0x000001"
            elif "mmcblk0/device/oemid" in path:
                content = "0x0001"
            elif "mmcblk0/size" in path:
                content = "1000000"

            # Mock for nvme0n1
            elif "nvme0n1/device/model" in path:
                content = "Test NVMe"
            elif "nvme0n1/queue/rotational" in path or "nvme0n1/removable" in path:
                content = "0"
            elif "nvme0n1/device/device/device" in path:
                content = "0x1234"
            elif "nvme0n1/device/device/vendor" in path:
                content = "0x5678"
            elif "nvme0n1/size" in path:
                content = "1000000"

            mock_file.read.return_value = content
            mock_file.__enter__.return_value = mock_file
            return mock_file

        monkeypatch.setattr(builtins, "open", mock_open)

        storage_info = fetch_storage_info()

        # Should only have 3 disks: sda, mmcblk0, nvme0n1
        assert len(storage_info.modules) == 3

        identifiers = [disk.identifier for disk in storage_info.modules]
        assert "sda" in identifiers
        assert "mmcblk0" in identifiers
        assert "nvme0n1" in identifiers

        # These should NOT be present
        assert "sda1" not in identifiers
        assert "sda2" not in identifiers
        assert "mmcblk0p1" not in identifiers
        assert "mmcblk0boot0" not in identifiers
        assert "mmcblk0boot1" not in identifiers
        assert "mmcblk0rpmb" not in identifiers
        assert "nvme0n1p1" not in identifiers
        assert "nvme0n1p2" not in identifiers
