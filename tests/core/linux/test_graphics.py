import builtins
import os
import posixpath
import subprocess
from unittest.mock import mock_open

from hwprobe.core.linux.graphics import (
    _check_gpu_class,
    _pcie_gen,
    _populate_amd_info,
    _populate_lspci_info,
    _populate_nvidia_info,
    _vram_amd,
    fetch_graphics_info,
)
from hwprobe.models.gpu_models import GPUInfo
from hwprobe.models.status_models import StatusType


class TestVramAmd:
    """Tests for _vram_amd function."""

    def test_vram_amd_success(self, monkeypatch):
        device = "0000:03:00.0"
        vram_path = f"/sys/bus/pci/devices/{device}/drm/card0/device/mem_info_vram_total"

        monkeypatch.setattr("glob.glob", lambda x: [vram_path])

        def mock_open_func(file, *args, **kwargs):
            if file == vram_path:
                # 8GB in bytes
                return mock_open(read_data=str(8 * 1024 * 1024 * 1024))()
            raise FileNotFoundError(file)

        monkeypatch.setattr(builtins, "open", mock_open_func)

        vram_mb = _vram_amd(device)
        assert vram_mb == 8192

    def test_vram_amd_4gb(self, monkeypatch):
        device = "0000:03:00.0"
        vram_path = f"/sys/bus/pci/devices/{device}/drm/card0/device/mem_info_vram_total"

        monkeypatch.setattr("glob.glob", lambda x: [vram_path])

        def mock_open_func(file, *args, **kwargs):
            if file == vram_path:
                # 4GB in bytes
                return mock_open(read_data=str(4 * 1024 * 1024 * 1024))()
            raise FileNotFoundError(file)

        monkeypatch.setattr(builtins, "open", mock_open_func)

        vram_mb = _vram_amd(device)
        assert vram_mb == 4096

    def test_vram_amd_no_file(self, monkeypatch):
        device = "0000:03:00.0"
        monkeypatch.setattr("glob.glob", lambda x: [])

        vram_mb = _vram_amd(device)
        assert vram_mb is None

    def test_vram_amd_exception(self, monkeypatch):
        def raise_error(x):
            raise Exception("Glob failed")

        monkeypatch.setattr("glob.glob", raise_error)

        assert _vram_amd("0000:00:00.0") is None

    def test_vram_amd_read_error(self, monkeypatch):
        device = "0000:03:00.0"
        vram_path = f"/sys/bus/pci/devices/{device}/drm/card0/device/mem_info_vram_total"

        monkeypatch.setattr("glob.glob", lambda x: [vram_path])

        def mock_open_func(file, *args, **kwargs):
            raise OSError("Read error")

        monkeypatch.setattr(builtins, "open", mock_open_func)

        vram_mb = _vram_amd(device)
        assert vram_mb is None


class TestPcieGen:
    """Tests for _pcie_gen function."""

    def test_pcie_gen_success_gen4(self, monkeypatch):
        device = "0000:01:00.0"
        path = f"/sys/bus/pci/devices/{device}/current_link_speed"

        monkeypatch.setattr(os.path, "exists", lambda x: x == path)

        def mock_open_func(file, *args, **kwargs):
            if file == path:
                return mock_open(read_data="16.0 GT/s")()
            raise FileNotFoundError(file)

        monkeypatch.setattr(builtins, "open", mock_open_func)

        gen = _pcie_gen(device)
        assert gen == 4

    def test_pcie_gen_success_gen3(self, monkeypatch):
        device = "0000:01:00.0"
        path = f"/sys/bus/pci/devices/{device}/current_link_speed"

        monkeypatch.setattr(os.path, "exists", lambda x: x == path)

        def mock_open_func(file, *args, **kwargs):
            if file == path:
                return mock_open(read_data="8.0 GT/s")()
            raise FileNotFoundError(file)

        monkeypatch.setattr(builtins, "open", mock_open_func)

        gen = _pcie_gen(device)
        assert gen == 3

    def test_pcie_gen_success_gen2(self, monkeypatch):
        device = "0000:01:00.0"
        path = f"/sys/bus/pci/devices/{device}/current_link_speed"

        monkeypatch.setattr(os.path, "exists", lambda x: x == path)

        def mock_open_func(file, *args, **kwargs):
            if file == path:
                return mock_open(read_data="5.0 GT/s")()
            raise FileNotFoundError(file)

        monkeypatch.setattr(builtins, "open", mock_open_func)

        gen = _pcie_gen(device)
        assert gen == 2

    def test_pcie_gen_success_gen1(self, monkeypatch):
        device = "0000:01:00.0"
        path = f"/sys/bus/pci/devices/{device}/current_link_speed"

        monkeypatch.setattr(os.path, "exists", lambda x: x == path)

        def mock_open_func(file, *args, **kwargs):
            if file == path:
                return mock_open(read_data="2.5 GT/s")()
            raise FileNotFoundError(file)

        monkeypatch.setattr(builtins, "open", mock_open_func)

        gen = _pcie_gen(device)
        assert gen == 1

    def test_pcie_gen_success_gen5(self, monkeypatch):
        device = "0000:01:00.0"
        path = f"/sys/bus/pci/devices/{device}/current_link_speed"

        monkeypatch.setattr(os.path, "exists", lambda x: x == path)

        def mock_open_func(file, *args, **kwargs):
            if file == path:
                return mock_open(read_data="32.0 GT/s")()
            raise FileNotFoundError(file)

        monkeypatch.setattr(builtins, "open", mock_open_func)

        gen = _pcie_gen(device)
        assert gen == 5

    def test_pcie_gen_with_suffix(self, monkeypatch):
        device = "0000:01:00.0"
        path = f"/sys/bus/pci/devices/{device}/current_link_speed"

        monkeypatch.setattr(os.path, "exists", lambda x: x == path)

        def mock_open_func(file, *args, **kwargs):
            if file == path:
                return mock_open(read_data="8.0 GT/s PCIe")()
            raise FileNotFoundError(file)

        monkeypatch.setattr(builtins, "open", mock_open_func)

        gen = _pcie_gen(device)
        assert gen == 3

    def test_pcie_gen_unknown_speed(self, monkeypatch):
        device = "0000:01:00.0"
        path = f"/sys/bus/pci/devices/{device}/current_link_speed"

        monkeypatch.setattr(os.path, "exists", lambda x: x == path)

        def mock_open_func(file, *args, **kwargs):
            if file == path:
                return mock_open(read_data="100.0 GT/s")()
            raise FileNotFoundError(file)

        monkeypatch.setattr(builtins, "open", mock_open_func)

        gen = _pcie_gen(device)
        assert gen is None

    def test_pcie_gen_file_not_found(self, monkeypatch):
        device = "0000:01:00.0"
        monkeypatch.setattr(os.path, "exists", lambda x: False)

        gen = _pcie_gen(device)
        assert gen is None

    def test_pcie_gen_read_exception(self, monkeypatch):
        device = "0000:01:00.0"
        path = f"/sys/bus/pci/devices/{device}/current_link_speed"

        monkeypatch.setattr(os.path, "exists", lambda x: x == path)

        def mock_open_func(file, *args, **kwargs):
            raise OSError("Read error")

        monkeypatch.setattr(builtins, "open", mock_open_func)

        gen = _pcie_gen(device)
        assert gen is None


class TestCheckGpuClass:
    """Tests for _check_gpu_class function."""

    def test_check_gpu_class_display_controller(self, monkeypatch):
        device = "0000:01:00.0"

        def mock_open_func(file, *args, **kwargs):
            if "class" in file:
                return mock_open(read_data="0x030000")()
            raise FileNotFoundError(file)

        monkeypatch.setattr(builtins, "open", mock_open_func)

        assert _check_gpu_class(device) is True

    def test_check_gpu_class_vga_controller(self, monkeypatch):
        device = "0000:01:00.0"

        def mock_open_func(file, *args, **kwargs):
            if "class" in file:
                return mock_open(read_data="0x030200")()  # 3D controller
            raise FileNotFoundError(file)

        monkeypatch.setattr(builtins, "open", mock_open_func)

        assert _check_gpu_class(device) is True

    def test_check_gpu_class_network_controller(self, monkeypatch):
        device = "0000:01:00.0"

        def mock_open_func(file, *args, **kwargs):
            if "class" in file:
                return mock_open(read_data="0x020000")()  # Network controller
            raise FileNotFoundError(file)

        monkeypatch.setattr(builtins, "open", mock_open_func)

        assert _check_gpu_class(device) is False

    def test_check_gpu_class_storage_controller(self, monkeypatch):
        device = "0000:01:00.0"

        def mock_open_func(file, *args, **kwargs):
            if "class" in file:
                return mock_open(read_data="0x010000")()  # Storage controller
            raise FileNotFoundError(file)

        monkeypatch.setattr(builtins, "open", mock_open_func)

        assert _check_gpu_class(device) is False


class TestPopulateAmdInfo:
    """Tests for _populate_amd_info function."""

    def test_populate_amd_info_with_vram(self, monkeypatch):
        device = "0000:03:00.0"
        gpu = GPUInfo()

        vram_path = f"/sys/bus/pci/devices/{device}/drm/card0/device/mem_info_vram_total"
        monkeypatch.setattr("glob.glob", lambda x: [vram_path])

        def mock_open_func(file, *args, **kwargs):
            if file == vram_path:
                return mock_open(read_data=str(8 * 1024 * 1024 * 1024))()
            raise FileNotFoundError(file)

        monkeypatch.setattr(builtins, "open", mock_open_func)

        gpu = _populate_amd_info(gpu, device)

        assert gpu.vram is not None
        assert gpu.vram.capacity == 8192

    def test_populate_amd_info_no_vram(self, monkeypatch):
        device = "0000:03:00.0"
        gpu = GPUInfo()

        monkeypatch.setattr("glob.glob", lambda x: [])

        gpu = _populate_amd_info(gpu, device)

        assert gpu.vram is None


class TestPopulateNvidiaInfo:
    """Tests for _populate_nvidia_info function."""

    def test_populate_nvidia_info_success(self, monkeypatch):
        device = "0000:01:00.0"
        gpu = GPUInfo()

        def mock_run(command, *args, **kwargs):
            if command[0] == "nvidia-smi":
                return subprocess.CompletedProcess(command, 0, stdout="GeForce RTX 3080, 16, 4, 10240\n")
            return subprocess.CompletedProcess(command, 1)

        monkeypatch.setattr(subprocess, "run", mock_run)

        gpu = _populate_nvidia_info(gpu, device)

        assert gpu.name == "GeForce RTX 3080"
        assert gpu.pcie_width == 16
        assert gpu.pcie_gen == 4
        assert gpu.vram.capacity == 10240

    def test_populate_nvidia_info_failure(self, monkeypatch):
        device = "0000:01:00.0"
        gpu = GPUInfo()

        def mock_run(command, *args, **kwargs):
            raise subprocess.CalledProcessError(1, command)

        monkeypatch.setattr(subprocess, "run", mock_run)

        try:
            _populate_nvidia_info(gpu, device)
            assert False, "Expected exception"
        except:
            pass  # Expected


class TestPopulateLspciInfo:
    """Tests for _populate_lspci_info function."""

    def test_populate_lspci_info_full(self, monkeypatch):
        device = "0000:01:00.0"
        gpu = GPUInfo()

        def mock_run(command, *args, **kwargs):
            if command[0] == "lspci":
                output = (
                    "Slot:\t01:00.0\n"
                    "Vendor:\tNVIDIA Corporation\n"
                    "Device:\tGeForce GTX 1080\n"
                    "SVendor:\tASUS\n"
                    "SDevice:\tROG STRIX GTX 1080\n"
                )
                return subprocess.CompletedProcess(command, 0, stdout=output)
            return subprocess.CompletedProcess(command, 1)

        monkeypatch.setattr(subprocess, "run", mock_run)

        gpu = _populate_lspci_info(gpu, device)

        assert gpu.manufacturer == "NVIDIA Corporation"
        assert gpu.name == "GeForce GTX 1080"
        assert gpu.subsystem_manufacturer == "ASUS"
        assert gpu.subsystem_model == "ROG STRIX GTX 1080"

    def test_populate_lspci_info_minimal(self, monkeypatch):
        device = "0000:01:00.0"
        gpu = GPUInfo()

        def mock_run(command, *args, **kwargs):
            if command[0] == "lspci":
                output = "Vendor:\tIntel Corporation\nDevice:\tUHD Graphics 620\n"
                return subprocess.CompletedProcess(command, 0, stdout=output)
            return subprocess.CompletedProcess(command, 1)

        monkeypatch.setattr(subprocess, "run", mock_run)

        gpu = _populate_lspci_info(gpu, device)

        assert gpu.manufacturer == "Intel Corporation"
        assert gpu.name == "UHD Graphics 620"
        assert gpu.subsystem_manufacturer is None
        assert gpu.subsystem_model is None

    def test_populate_lspci_info_failure(self, monkeypatch):
        device = "0000:01:00.0"
        gpu = GPUInfo()

        def mock_run(command, *args, **kwargs):
            raise FileNotFoundError("lspci not found")

        monkeypatch.setattr(subprocess, "run", mock_run)

        try:
            _populate_lspci_info(gpu, device)
            assert False, "Expected exception"
        except FileNotFoundError:
            pass  # Expected


class TestFetchGraphicsInfo:
    """Tests for fetch_graphics_info function."""

    def test_fetch_graphics_info_root_not_found(self, monkeypatch):
        monkeypatch.setattr(os.path, "exists", lambda x: False)

        info = fetch_graphics_info()

        assert info.status.type == StatusType.FAILED
        assert "not found" in info.status.messages[0]
        assert len(info.modules) == 0

    def test_fetch_graphics_info_success_intel(self, monkeypatch):
        monkeypatch.setattr(os.path, "exists", lambda x: True)
        monkeypatch.setattr(os, "listdir", lambda x: ["0000:00:02.0"])

        file_contents = {
            "class": "0x030000",
            "vendor": "0x8086",
            "device": "0x5917",
            "current_link_width": "0",
            "current_link_speed": "8.0 GT/s",
            "firmware_node/path": "\\_SB.PCI0.GFX0",
        }

        def custom_open(path, *args, **kwargs):
            filename = posixpath.basename(path)
            if filename == "path" and "firmware_node" in path:
                return mock_open(read_data=file_contents["firmware_node/path"])()
            if filename in file_contents:
                return mock_open(read_data=file_contents[filename])()
            raise FileNotFoundError(path)

        monkeypatch.setattr(builtins, "open", custom_open)
        monkeypatch.setattr("hwprobe.core.linux.graphics.pci_path_linux", lambda x: "PciRoot(0x0)/Pci(0x2,0x0)")

        def mock_run(command, *args, **kwargs):
            if command[0] == "lspci":
                output = "Vendor:\tIntel Corporation\nDevice:\tUHD Graphics 620\nSVendor:\tLenovo\nSDevice:\tThinkPad\n"
                return subprocess.CompletedProcess(command, 0, stdout=output)
            return subprocess.CompletedProcess(command, 1)

        monkeypatch.setattr(subprocess, "run", mock_run)

        info = fetch_graphics_info()

        assert info.status.type == StatusType.SUCCESS
        assert len(info.modules) == 1

        gpu = info.modules[0]
        assert gpu.vendor_id == "0x8086"
        assert gpu.device_id == "0x5917"
        assert gpu.acpi_path == "\\_SB.PCI0.GFX0"
        assert gpu.manufacturer == "Intel Corporation"
        assert gpu.name == "UHD Graphics 620"
        assert gpu.pcie_gen == 3

    def test_fetch_graphics_info_nvidia(self, monkeypatch):
        monkeypatch.setattr(os.path, "exists", lambda x: True)
        monkeypatch.setattr(os, "listdir", lambda x: ["0000:01:00.0"])

        file_contents = {
            "class": "0x030000",
            "vendor": "0x10de",
            "device": "0x1c03",
            "current_link_width": "16",
            "current_link_speed": "8.0 GT/s",
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

        def mock_run(command, *args, **kwargs):
            if command[0] == "nvidia-smi":
                return subprocess.CompletedProcess(command, 0, stdout="GeForce GTX 1060, 16, 3, 6144\n")
            if command[0] == "lspci":
                output = "Vendor:\tNVIDIA\nDevice:\tGeForce GTX 1060\n"
                return subprocess.CompletedProcess(command, 0, stdout=output)
            return subprocess.CompletedProcess(command, 1)

        monkeypatch.setattr(subprocess, "run", mock_run)

        info = fetch_graphics_info()

        assert len(info.modules) == 1
        gpu = info.modules[0]
        assert gpu.vendor_id == "0x10de"
        assert gpu.vram is not None
        assert gpu.vram.capacity == 6144

    def test_fetch_graphics_info_amd(self, monkeypatch):
        monkeypatch.setattr(os.path, "exists", lambda x: True)
        monkeypatch.setattr(os, "listdir", lambda x: ["0000:03:00.0"])

        file_contents = {
            "class": "0x030000",
            "vendor": "0x1002",
            "device": "0x731f",
            "current_link_width": "16",
            "current_link_speed": "16.0 GT/s",
            "firmware_node/path": "\\_SB.PCI0.PEG0.PEGP",
        }

        def custom_open(path, *args, **kwargs):
            filename = posixpath.basename(path)
            if filename == "path" and "firmware_node" in path:
                return mock_open(read_data=file_contents["firmware_node/path"])()
            if filename in file_contents:
                return mock_open(read_data=file_contents[filename])()
            if filename == "mem_info_vram_total":
                return mock_open(read_data=str(8 * 1024 * 1024 * 1024))()
            raise FileNotFoundError(path)

        monkeypatch.setattr(builtins, "open", custom_open)
        monkeypatch.setattr("hwprobe.core.linux.graphics.pci_path_linux", lambda x: "PciRoot(0x0)/Pci(0x3,0x0)")
        monkeypatch.setattr(
            "glob.glob", lambda x: ["/sys/bus/pci/devices/0000:03:00.0/drm/card0/device/mem_info_vram_total"]
        )

        def mock_run(command, *args, **kwargs):
            if command[0] == "lspci":
                output = "Vendor:\tAMD\nDevice:\tRadeon RX 5700 XT\n"
                return subprocess.CompletedProcess(command, 0, stdout=output)
            return subprocess.CompletedProcess(command, 1)

        monkeypatch.setattr(subprocess, "run", mock_run)

        info = fetch_graphics_info()

        assert len(info.modules) == 1
        gpu = info.modules[0]
        assert gpu.vendor_id == "0x1002"
        assert gpu.vram is not None
        assert gpu.vram.capacity == 8192
        assert gpu.pcie_gen == 4

    def test_fetch_graphics_info_skip_non_display(self, monkeypatch):
        monkeypatch.setattr(os.path, "exists", lambda x: True)
        monkeypatch.setattr(os, "listdir", lambda x: ["0000:04:00.0"])

        file_contents = {
            "class": "0x020000",  # Network Controller
        }

        def custom_open(path, *args, **kwargs):
            filename = posixpath.basename(path)
            if filename in file_contents:
                return mock_open(read_data=file_contents[filename])()
            raise FileNotFoundError(path)

        monkeypatch.setattr(builtins, "open", custom_open)

        info = fetch_graphics_info()

        assert len(info.modules) == 0
        assert info.status.type == StatusType.SUCCESS

    def test_fetch_graphics_info_partial_failure(self, monkeypatch):
        monkeypatch.setattr(os.path, "exists", lambda x: True)
        monkeypatch.setattr(os, "listdir", lambda x: ["0000:01:00.0"])

        def custom_open(path, *args, **kwargs):
            filename = posixpath.basename(path)
            if filename == "class":
                return mock_open(read_data="0x030000")()
            if filename == "vendor":
                raise OSError("Permission denied")
            if filename == "device":
                return mock_open(read_data="0x1234")()
            raise OSError("File not found")

        monkeypatch.setattr(builtins, "open", custom_open)

        def mock_run(*args, **kwargs):
            raise FileNotFoundError("lspci not found")

        monkeypatch.setattr(subprocess, "run", mock_run)

        info = fetch_graphics_info()

        assert info.status.type == StatusType.PARTIAL
        assert len(info.modules) == 1

    def test_fetch_graphics_info_acpi_path_failure(self, monkeypatch):
        monkeypatch.setattr(os.path, "exists", lambda x: True)
        monkeypatch.setattr(os, "listdir", lambda x: ["0000:00:02.0"])

        file_contents = {
            "class": "0x030000",
            "vendor": "0x8086",
            "device": "0x5917",
            "current_link_width": "0",
            "current_link_speed": "8.0 GT/s",
        }

        def custom_open(path, *args, **kwargs):
            filename = posixpath.basename(path)
            if filename == "path" and "firmware_node" in path:
                raise FileNotFoundError("No ACPI path")
            if filename in file_contents:
                return mock_open(read_data=file_contents[filename])()
            raise FileNotFoundError(path)

        monkeypatch.setattr(builtins, "open", custom_open)
        monkeypatch.setattr("hwprobe.core.linux.graphics.pci_path_linux", lambda x: "PciRoot(0x0)/Pci(0x2,0x0)")
        monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: subprocess.CompletedProcess(args, 0, stdout=""))

        info = fetch_graphics_info()

        assert len(info.modules) == 1
        gpu = info.modules[0]
        assert gpu.vendor_id == "0x8086"
        assert gpu.acpi_path is None
        assert info.status.type == StatusType.PARTIAL
        assert any("ACPI path" in msg for msg in info.status.messages)

    def test_fetch_graphics_info_pci_path_failure(self, monkeypatch):
        monkeypatch.setattr(os.path, "exists", lambda x: True)
        monkeypatch.setattr(os, "listdir", lambda x: ["0000:00:02.0"])

        file_contents = {
            "class": "0x030000",
            "vendor": "0x8086",
            "device": "0x5917",
            "current_link_width": "0",
            "current_link_speed": "8.0 GT/s",
            "firmware_node/path": "\\_SB.PCI0.GFX0",
        }

        def custom_open(path, *args, **kwargs):
            filename = posixpath.basename(path)
            if filename == "path" and "firmware_node" in path:
                return mock_open(read_data=file_contents["firmware_node/path"])()
            if filename in file_contents:
                return mock_open(read_data=file_contents[filename])()
            raise FileNotFoundError(path)

        monkeypatch.setattr(builtins, "open", custom_open)

        def mock_pci_path(device):
            raise Exception("PCI path failed")

        monkeypatch.setattr("hwprobe.core.linux.graphics.pci_path_linux", mock_pci_path)
        monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: subprocess.CompletedProcess(args, 0, stdout=""))

        info = fetch_graphics_info()

        assert len(info.modules) == 1
        gpu = info.modules[0]
        assert gpu.pci_path is None
        assert info.status.type == StatusType.PARTIAL
        assert any("PCI path" in msg for msg in info.status.messages)

    def test_fetch_graphics_info_nvidia_failure(self, monkeypatch):
        monkeypatch.setattr(os.path, "exists", lambda x: True)
        monkeypatch.setattr(os, "listdir", lambda x: ["0000:01:00.0"])

        file_contents = {
            "class": "0x030000",
            "vendor": "0x10de",
            "device": "0x1c03",
            "current_link_width": "16",
            "current_link_speed": "8.0 GT/s",
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

        def mock_run(command, *args, **kwargs):
            if command[0] == "nvidia-smi":
                raise subprocess.CalledProcessError(1, command)
            return subprocess.CompletedProcess(command, 0, stdout="")

        monkeypatch.setattr(subprocess, "run", mock_run)

        info = fetch_graphics_info()

        assert len(info.modules) == 1
        gpu = info.modules[0]
        assert gpu.vendor_id == "0x10de"
        assert gpu.vram is None
        assert info.status.type == StatusType.PARTIAL
        assert any("Could not get additional GPU info" in msg for msg in info.status.messages)

    def test_fetch_graphics_info_lspci_failure(self, monkeypatch):
        monkeypatch.setattr(os.path, "exists", lambda x: True)
        monkeypatch.setattr(os, "listdir", lambda x: ["0000:00:02.0"])

        file_contents = {
            "class": "0x030000",
            "vendor": "0x8086",
            "device": "0x5917",
            "current_link_width": "0",
            "current_link_speed": "8.0 GT/s",
            "firmware_node/path": "\\_SB.PCI0.GFX0",
        }

        def custom_open(path, *args, **kwargs):
            filename = posixpath.basename(path)
            if filename == "path" and "firmware_node" in path:
                return mock_open(read_data=file_contents["firmware_node/path"])()
            if filename in file_contents:
                return mock_open(read_data=file_contents[filename])()
            raise FileNotFoundError(path)

        monkeypatch.setattr(builtins, "open", custom_open)
        monkeypatch.setattr("hwprobe.core.linux.graphics.pci_path_linux", lambda x: "PciRoot(0x0)/Pci(0x2,0x0)")

        def mock_run(command, *args, **kwargs):
            if command[0] == "lspci":
                raise FileNotFoundError("lspci not found")
            return subprocess.CompletedProcess(command, 0, stdout="")

        monkeypatch.setattr(subprocess, "run", mock_run)

        info = fetch_graphics_info()

        assert len(info.modules) == 1
        gpu = info.modules[0]
        assert gpu.vendor_id == "0x8086"
        assert info.status.type == StatusType.PARTIAL
        assert any("LSPCI" in msg for msg in info.status.messages)

    def test_fetch_graphics_info_pcie_gen_failure(self, monkeypatch):
        monkeypatch.setattr(os.path, "exists", lambda x: "/current_link_speed" not in x)
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
                return mock_open(read_data=file_contents["firmware_node/path"])()
            if filename in file_contents:
                return mock_open(read_data=file_contents[filename])()
            raise FileNotFoundError(path)

        monkeypatch.setattr(builtins, "open", custom_open)
        monkeypatch.setattr("hwprobe.core.linux.graphics.pci_path_linux", lambda x: "PciRoot(0x0)/Pci(0x2,0x0)")
        monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: subprocess.CompletedProcess(args, 0, stdout=""))

        info = fetch_graphics_info()

        assert len(info.modules) == 1
        gpu = info.modules[0]
        assert gpu.pcie_gen is None
        assert info.status.type == StatusType.PARTIAL
        assert any("PCI gen" in msg for msg in info.status.messages)

    def test_fetch_graphics_info_class_read_failure(self, monkeypatch):
        monkeypatch.setattr(os.path, "exists", lambda x: True)
        monkeypatch.setattr(os, "listdir", lambda x: ["0000:00:02.0"])

        def custom_open(path, *args, **kwargs):
            if "class" in path:
                raise OSError("Permission denied")
            raise FileNotFoundError(path)

        monkeypatch.setattr(builtins, "open", custom_open)

        info = fetch_graphics_info()

        # Device should be skipped due to class read failure
        assert len(info.modules) == 0
        assert info.status.type == StatusType.PARTIAL
        assert any("Could not open file" in msg for msg in info.status.messages)
