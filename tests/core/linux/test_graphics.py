import builtins
import os
import pytest
import posixpath
from unittest.mock import mock_open

from hwprobe.core.linux.common import _read_from_sysfs
from hwprobe.core.linux.graphics import _check_gpu_class, _pcie_gen, fetch_graphics_info
from hwprobe.models.status_models import StatusType

class TestPcieGen:
    """Tests for _pcie_gen."""

    def test_pcie_gen_success_gen4(self, monkeypatch):
        device = "0000:01:00.0"
        path = f"/sys/bus/pci/devices/{device}/current_link_speed"

        monkeypatch.setattr(posixpath, "exists", lambda x: x == path)

        def mock_open_func(file, *args, **kwargs):
            if file == path:
                return mock_open(read_data="16.0 GT/s")()
            raise FileNotFoundError(file)

        monkeypatch.setattr(builtins, "open", mock_open_func)

        speed = _read_from_sysfs(path)
        assert speed is not None

        gen = _pcie_gen(speed)
        assert gen == 4

    def test_pcie_gen_success_gen3(self, monkeypatch):
        device = "0000:01:00.0"
        path = f"/sys/bus/pci/devices/{device}/current_link_speed"

        monkeypatch.setattr(posixpath, "exists", lambda x: x == path)

        def mock_open_func(file, *args, **kwargs):
            if file == path:
                return mock_open(read_data="8.0 GT/s")()
            raise FileNotFoundError(file)

        monkeypatch.setattr(builtins, "open", mock_open_func)

        speed = _read_from_sysfs(path)
        assert speed is not None

        gen = _pcie_gen(speed)
        assert gen == 3

    def test_pcie_gen_success_gen2(self, monkeypatch):
        device = "0000:01:00.0"
        path = f"/sys/bus/pci/devices/{device}/current_link_speed"

        monkeypatch.setattr(posixpath, "exists", lambda x: x == path)

        def mock_open_func(file, *args, **kwargs):
            if file == path:
                return mock_open(read_data="5.0 GT/s")()
            raise FileNotFoundError(file)

        monkeypatch.setattr(builtins, "open", mock_open_func)

        speed = _read_from_sysfs(path)
        assert speed is not None

        gen = _pcie_gen(speed)
        assert gen == 2

    def test_pcie_gen_success_gen1(self, monkeypatch):
        device = "0000:01:00.0"
        path = f"/sys/bus/pci/devices/{device}/current_link_speed"

        monkeypatch.setattr(posixpath, "exists", lambda x: x == path)

        def mock_open_func(file, *args, **kwargs):
            if file == path:
                return mock_open(read_data="2.5 GT/s")()
            raise FileNotFoundError(file)

        monkeypatch.setattr(builtins, "open", mock_open_func)

        speed = _read_from_sysfs(path)
        assert speed is not None

        gen = _pcie_gen(speed)
        assert gen == 1

    def test_pcie_gen_success_gen5(self, monkeypatch):
        device = "0000:01:00.0"
        path = f"/sys/bus/pci/devices/{device}/current_link_speed"

        monkeypatch.setattr(posixpath, "exists", lambda x: x == path)

        def mock_open_func(file, *args, **kwargs):
            if file == path:
                return mock_open(read_data="32.0 GT/s")()
            raise FileNotFoundError(file)

        monkeypatch.setattr(builtins, "open", mock_open_func)

        speed = _read_from_sysfs(path)
        assert speed is not None

        gen = _pcie_gen(speed)
        assert gen == 5

    def test_pcie_gen_with_suffix(self, monkeypatch):
        device = "0000:01:00.0"
        path = f"/sys/bus/pci/devices/{device}/current_link_speed"

        monkeypatch.setattr(posixpath, "exists", lambda x: x == path)

        def mock_open_func(file, *args, **kwargs):
            if file == path:
                return mock_open(read_data="8.0 GT/s PCIe")()
            raise FileNotFoundError(file)

        monkeypatch.setattr(builtins, "open", mock_open_func)

        speed = _read_from_sysfs(path)
        assert speed is not None

        gen = _pcie_gen(speed)
        assert gen == 3

    def test_pcie_gen_unknown_speed(self, monkeypatch):
        device = "0000:01:00.0"
        path = f"/sys/bus/pci/devices/{device}/current_link_speed"

        monkeypatch.setattr(posixpath, "exists", lambda x: x == path)

        def mock_open_func(file, *args, **kwargs):
            if file == path:
                return mock_open(read_data="100.0 GT/s")()
            raise FileNotFoundError(file)

        monkeypatch.setattr(builtins, "open", mock_open_func)

        speed = _read_from_sysfs(path)
        assert speed is not None

        gen = _pcie_gen(speed)
        assert gen is None

    def test_pcie_gen_file_not_found(self, monkeypatch):
        device = "0000:01:00.0"
        path = f"/sys/bus/pci/devices/{device}/current_link_speed"

        monkeypatch.setattr(posixpath, "exists", lambda x: False)

        speed = _read_from_sysfs(path)
        assert speed is None

        gen = _pcie_gen(speed)
        assert gen is None

    def test_pcie_gen_read_exception(self, monkeypatch):
        device = "0000:01:00.0"
        path = f"/sys/bus/pci/devices/{device}/current_link_speed"

        monkeypatch.setattr(posixpath, "exists", lambda x: x == path)

        def mock_open_func(file, *args, **kwargs):
            raise OSError("Read error")

        monkeypatch.setattr(builtins, "open", mock_open_func)

        speed = _read_from_sysfs(path)
        assert speed is None

        gen = _pcie_gen(speed)
        assert gen is None

@pytest.mark.parametrize("bdf", ["0000:01:00.0"])
class TestCheckGpuClass:
    """Tests for _check_gpu_class."""

    @pytest.mark.parametrize(
        ("device_class", "expected"),
        [
            ("0x030000", True),
            ("0x030200", True),
            ("0x020000", False),
        ],
    )
    def test_check_gpu_class(self, bdf, monkeypatch, device_class, expected):
        monkeypatch.setattr(
            "hwprobe.core.linux.graphics._read_from_sysfs",
            lambda *args: device_class,
        )
        assert _check_gpu_class(bdf) is expected


class TestFetchGraphicsInfo:
    """Tests for fetch_graphics_info."""

    def test_fetch_graphics_info_root_not_found(self, monkeypatch):
        monkeypatch.setattr(posixpath, "exists", lambda x: False)

        info = fetch_graphics_info()

        assert info.status.type == StatusType.FAILED
        assert "not found" in info.status.messages[0]
        assert len(info.modules) == 0

    def test_fetch_graphics_info_success_intel(self, monkeypatch):
        monkeypatch.setattr(posixpath, "exists", lambda x: True)
        monkeypatch.setattr(os, "listdir", lambda x: ["0000:00:02.0"])

        file_contents = {
            "class": "0x030000",
            "vendor": "0x8086",
            "device": "0x5917",
            "current_link_width": "16",
            "current_link_speed": "8.0 GT/s",
            "max_link_width": "16",
            "max_link_speed": "8.0 GT/s",
            "firmware_node/path": "\\_SB.PCI0.GFX0",
        }

        def custom_open(path, *args, **kwargs):
            filename = posixpath.basename(path)
            filename = posixpath.basename(path)
            if filename == "path" and "firmware_node" in path:
                return mock_open(read_data=file_contents["firmware_node/path"])()
            if filename in file_contents:
                return mock_open(read_data=file_contents[filename])()
            raise FileNotFoundError(path)

        monkeypatch.setattr(builtins, "open", custom_open)
        monkeypatch.setattr("hwprobe.core.linux.graphics.pci_path_linux", lambda x: "PciRoot(0x0)/Pci(0x2,0x0)")
        monkeypatch.setattr("hwprobe.core.linux.graphics.NATIVE_AVAILABLE", False)

        info = fetch_graphics_info()

        assert info.status.type == StatusType.PARTIAL
        assert len(info.modules) == 1
        gpu = info.modules[0]
        assert gpu.vendor_id == "0x8086"
        assert gpu.device_id == "0x5917"
        assert gpu.acpi_path == "\\_SB.PCI0.GFX0"
        assert gpu.pcie_gen == 3
        assert gpu.pcie_width == 16
        # Uncomment this once PCI-IDs parser is implemented
        # assert gpu.manufacturer == "Intel Corporation"

    def test_fetch_graphics_info_native_nvidia(self, monkeypatch):
        monkeypatch.setattr(posixpath, "exists", lambda x: True)
        monkeypatch.setattr(os, "listdir", lambda x: ["0000:01:00.0"])

        file_contents = {
            "class": "0x030000",
            "vendor": "0x10de",
            "device": "0x1c03",
            "current_link_width": "16",
            "current_link_speed": "8.0 GT/s",
            "max_link_width": "16",
            "max_link_speed": "8.0 GT/s",
            "firmware_node/path": "\\_SB.PCI0.PEG0.PEGP",
        }

        def custom_open(path, *args, **kwargs):
            filename = posixpath.basename(path)
            if filename == "path" and "firmware_node" in path:
                return mock_open(read_data=file_contents["firmware_node/path"])()
            if filename in file_contents:
                return mock_open(read_data=file_contents[filename])()
            raise FileNotFoundError(path)

        monkeypatch.setattr(builtins, "open", custom_open)
        monkeypatch.setattr("hwprobe.core.linux.graphics.pci_path_linux", lambda x: "PciRoot(0x0)/Pci(0x1,0x0)")
        monkeypatch.setattr("hwprobe.core.linux.graphics.NATIVE_AVAILABLE", True)
        monkeypatch.setattr(
            "hwprobe.core.linux.graphics.native_gpu.get_gpu_info",
            lambda *args, **kwargs: type(
                "Native",
                (),
                {"name": "GeForce GTX 1060", "vram_total_mb": 6144, "vram_used_mb": 0},
            )(),
        )

        info = fetch_graphics_info()

        assert len(info.modules) == 1
        gpu = info.modules[0]
        assert gpu.vendor_id == "0x10de"
        assert gpu.name == "GeForce GTX 1060"
        assert gpu.vram is not None
        assert gpu.vram.capacity == 6144

    def test_fetch_graphics_info_native_amd(self, monkeypatch):
        monkeypatch.setattr(posixpath, "exists", lambda x: True)
        monkeypatch.setattr(os, "listdir", lambda x: ["0000:03:00.0"])

        file_contents = {
            "class": "0x030000",
            "vendor": "0x1002",
            "device": "0x731f",
            "current_link_width": "16",
            "current_link_speed": "16.0 GT/s",
            "max_link_width": "16",
            "max_link_speed": "16.0 GT/s",
            "firmware_node/path": "\\_SB.PCI0.PEG0.PEGP",
        }

        def custom_open(path, *args, **kwargs):
            filename = posixpath.basename(path)
            if filename == "path" and "firmware_node" in path:
                return mock_open(read_data=file_contents["firmware_node/path"])()
            if filename in file_contents:
                return mock_open(read_data=file_contents[filename])()
            raise FileNotFoundError(path)

        monkeypatch.setattr(builtins, "open", custom_open)
        monkeypatch.setattr("hwprobe.core.linux.graphics.pci_path_linux", lambda x: "PciRoot(0x0)/Pci(0x3,0x0)")
        monkeypatch.setattr("hwprobe.core.linux.graphics.NATIVE_AVAILABLE", True)
        monkeypatch.setattr(
            "hwprobe.core.linux.graphics.native_gpu.get_gpu_info",
            lambda *args, **kwargs: type(
                "Native",
                (),
                {"name": "Radeon RX 5700 XT", "vram_total_mb": 8192, "vram_used_mb": 0},
            )(),
        )

        info = fetch_graphics_info()

        assert len(info.modules) == 1
        gpu = info.modules[0]
        assert gpu.vendor_id == "0x1002"
        assert gpu.name == "Radeon RX 5700 XT"
        assert gpu.vram is not None
        assert gpu.vram.capacity == 8192
        assert gpu.pcie_gen == 4

    def test_fetch_graphics_info_skip_non_display(self, monkeypatch):
        monkeypatch.setattr(posixpath, "exists", lambda x: True)
        monkeypatch.setattr(os, "listdir", lambda x: ["0000:04:00.0"])

        def custom_open(path, *args, **kwargs):
            if "class" in path:
                return mock_open(read_data="0x020000")()
            raise FileNotFoundError(path)

        monkeypatch.setattr(builtins, "open", custom_open)

        info = fetch_graphics_info()

        assert len(info.modules) == 0
        assert info.status.type == StatusType.SUCCESS

    def test_fetch_graphics_info_partial_failure(self, monkeypatch):
        monkeypatch.setattr(posixpath, "exists", lambda x: True)
        monkeypatch.setattr(posixpath, "exists", lambda x: True)
        monkeypatch.setattr(os, "listdir", lambda x: ["0000:01:00.0"])

        def custom_open(path, *args, **kwargs):
            filename = posixpath.basename(path)
            filename = posixpath.basename(path)
            if filename == "class":
                return mock_open(read_data="0x030000")()
            if filename == "vendor":
                raise OSError("Permission denied")
            if filename == "device":
                return mock_open(read_data="0x1234")()
            if filename in {"current_link_speed", "max_link_speed"}:
                return mock_open(read_data="8.0 GT/s")()
            if filename in {"current_link_width", "max_link_width"}:
                return mock_open(read_data="16")()
            if filename == "path" and "firmware_node" in path:
                return mock_open(read_data="\\_SB.PCI0.GFX0")()
            raise FileNotFoundError(path)

        monkeypatch.setattr(builtins, "open", custom_open)
        monkeypatch.setattr("hwprobe.core.linux.graphics.pci_path_linux", lambda x: "PciRoot(0x0)/Pci(0x1,0x0)")

        info = fetch_graphics_info()

        assert info.status.type == StatusType.PARTIAL
        assert len(info.modules) == 1
        assert any("Could not read vendor ID" in msg for msg in info.status.messages)

    def test_fetch_graphics_info_acpi_path_failure(self, monkeypatch):
        monkeypatch.setattr(posixpath, "exists", lambda x: True)
        monkeypatch.setattr(os, "listdir", lambda x: ["0000:00:02.0"])

        file_contents = {
            "class": "0x030000",
            "vendor": "0x8086",
            "device": "0x5917",
            "current_link_width": "16",
            "current_link_speed": "8.0 GT/s",
            "max_link_width": "16",
            "max_link_speed": "8.0 GT/s",
        }


        def custom_open(path, *args, **kwargs):
            filename = posixpath.basename(path)
            filename = posixpath.basename(path)
            if filename == "path" and "firmware_node" in path:
                raise FileNotFoundError("No ACPI path")
            if filename in file_contents:
                return mock_open(read_data=file_contents[filename])()
            raise FileNotFoundError(path)

        monkeypatch.setattr(builtins, "open", custom_open)
        monkeypatch.setattr("hwprobe.core.linux.graphics.pci_path_linux", lambda x: "PciRoot(0x0)/Pci(0x2,0x0)")

        info = fetch_graphics_info()

        assert len(info.modules) == 1
        gpu = info.modules[0]
        assert gpu.vendor_id == "0x8086"
        assert gpu.acpi_path is None
        assert info.status.type == StatusType.PARTIAL
        assert any("ACPI path" in msg for msg in info.status.messages)

    def test_fetch_graphics_info_pci_path_failure(self, monkeypatch):
        monkeypatch.setattr(posixpath, "exists", lambda x: True)
        monkeypatch.setattr(posixpath, "exists", lambda x: True)
        monkeypatch.setattr(os, "listdir", lambda x: ["0000:00:02.0"])

        file_contents = {
            "class": "0x030000",
            "vendor": "0x8086",
            "device": "0x5917",
            "current_link_width": "16",
            "current_link_speed": "8.0 GT/s",
            "max_link_width": "16",
            "max_link_speed": "8.0 GT/s",
        }

        def custom_open(path, *args, **kwargs):
            filename = posixpath.basename(path)
            if filename == "path" and "firmware_node" in path:
                return mock_open(read_data=file_contents["firmware_node/path"])()
            if filename in file_contents:
                return mock_open(read_data=file_contents[filename])()
            raise FileNotFoundError(path)

        monkeypatch.setattr(builtins, "open", custom_open)
        monkeypatch.setattr("hwprobe.core.linux.graphics.pci_path_linux", lambda x: None)

        info = fetch_graphics_info()

        assert len(info.modules) == 1
        gpu = info.modules[0]
        assert gpu.pci_path is None
        assert info.status.type == StatusType.PARTIAL
        assert any("PCI path" in msg for msg in info.status.messages)

    def test_fetch_graphics_info_nvidia_failure(self, monkeypatch):
        monkeypatch.setattr(posixpath, "exists", lambda x: True)
        monkeypatch.setattr(os, "listdir", lambda x: ["0000:01:00.0"])

        file_contents = {
            "class": "0x030000",
            "vendor": "0x10de",
            "device": "0x1c03",
            "current_link_width": "16",
            "current_link_speed": "8.0 GT/s",
            "max_link_width": "16",
            "max_link_speed": "8.0 GT/s",
        }

        def custom_open(path, *args, **kwargs):
            filename = posixpath.basename(path)
            if filename == "path" and "firmware_node" in path:
                return mock_open(read_data=file_contents["firmware_node/path"])()
            if filename in file_contents:
                return mock_open(read_data=file_contents[filename])()
            raise FileNotFoundError(path)

        monkeypatch.setattr(builtins, "open", custom_open)
        monkeypatch.setattr("hwprobe.core.linux.graphics.pci_path_linux", lambda x: "PciRoot(0x0)/Pci(0x1,0x0)")
        monkeypatch.setattr("hwprobe.core.linux.graphics.NATIVE_AVAILABLE", True)
        monkeypatch.setattr(
            "hwprobe.core.linux.graphics.native_gpu.get_gpu_info",
            lambda *args, **kwargs: type(
                "Native",
                (),
                {"name": "GeForce GTX 1060", "vram_total_mb": 6144, "vram_used_mb": 0},
            )(),
        )

        info = fetch_graphics_info()

        assert len(info.modules) == 1
        gpu = info.modules[0]
        assert gpu.vendor_id == "0x10de"
        assert gpu.name == "GeForce GTX 1060"
        assert gpu.vram is not None
        assert gpu.vram.capacity == 6144

    def test_fetch_graphics_info_native_failure(self, monkeypatch):
        monkeypatch.setattr(posixpath, "exists", lambda x: True)
        monkeypatch.setattr(os, "listdir", lambda x: ["0000:00:02.0"])

        file_contents = {
            "class": "0x030000",
            "vendor": "0x8086",
            "device": "0x5917",
            "current_link_width": "16",
            "max_link_width": "16",
            "current_link_speed": "8.0 GT/s",
            "max_link_speed": "8.0 GT/s",
        }

        def custom_open(path, *args, **kwargs):
            filename = posixpath.basename(path)
            if filename == "path" and "firmware_node" in path:
                return mock_open(read_data="\\_SB.PCI0.GFX0")()
            if filename in file_contents:
                return mock_open(read_data=file_contents[filename])()
            raise FileNotFoundError(path)

        monkeypatch.setattr(builtins, "open", custom_open)
        monkeypatch.setattr("hwprobe.core.linux.graphics.pci_path_linux", lambda x: "PciRoot(0x0)/Pci(0x2,0x0)")
        monkeypatch.setattr("hwprobe.core.linux.graphics.NATIVE_AVAILABLE", True)
        monkeypatch.setattr("hwprobe.core.linux.graphics.native_gpu.get_gpu_info", lambda *args, **kwargs: None)

        info = fetch_graphics_info()

        assert len(info.modules) == 1
        gpu = info.modules[0]
        assert gpu.vendor_id == "0x8086"
        assert info.status.type == StatusType.PARTIAL
        assert any("Native GPU info library could not fetch GPU name or VRAM" in msg for msg in info.status.messages)

    def test_fetch_graphics_info_pcie_gen_failure(self, monkeypatch):
        monkeypatch.setattr(posixpath, "exists", lambda x: "/current_link_speed" not in str(x))
        monkeypatch.setattr(os, "listdir", lambda x: ["0000:00:02.0"])

        file_contents = {
            "class": "0x030000",
            "vendor": "0x8086",
            "device": "0x5917",
            "current_link_width": "0",
            "firmware_node/path": "\\_SB.PCI0.GFX0",
        }

        def custom_open(path, *args, **kwargs):
            filename = posixpath.basename(path)
            if filename == "path" and "firmware_node" in path:
                return mock_open(read_data="\\_SB.PCI0.GFX0")()
            if filename in file_contents:
                return mock_open(read_data=file_contents[filename])()
            raise FileNotFoundError(path)

        monkeypatch.setattr(builtins, "open", custom_open)
        monkeypatch.setattr("hwprobe.core.linux.graphics.pci_path_linux", lambda x: "PciRoot(0x0)/Pci(0x2,0x0)")

        info = fetch_graphics_info()

        assert len(info.modules) == 1
        gpu = info.modules[0]
        assert gpu.pcie_width is None
        assert gpu.pcie_gen is None
        assert info.status.type == StatusType.PARTIAL
        assert any("current link speed" in msg for msg in info.status.messages)

    def test_fetch_graphics_info_class_read_failure(self, monkeypatch):
        monkeypatch.setattr(posixpath, "exists", lambda x: True)
        monkeypatch.setattr(os, "listdir", lambda x: ["0000:00:02.0"])

        def custom_open(path, *args, **kwargs):
            if "class" in path:
                raise OSError("Permission denied")
            raise FileNotFoundError(path)

        monkeypatch.setattr(builtins, "open", custom_open)

        info = fetch_graphics_info()

        assert len(info.modules) == 0
        assert info.status.type == StatusType.PARTIAL
        assert any("Could not open file" in msg for msg in info.status.messages)
