import glob
import os
import posixpath
import subprocess
from typing import Optional

from hwprobe.core.linux.common import pci_path_linux
from hwprobe.models.gpu_models import GPUInfo, GraphicsInfo
from hwprobe.models.size_models import Megabyte
from hwprobe.models.status_models import StatusType
from hwprobe.util.nvidia import fetch_gpu_details_nvidia

# Currently, the info in /sys/class/drm/cardX is being used.
# todo: Check if lspci and lshw -c display can be used
# https://unix.stackexchange.com/questions/393/how-to-check-how-many-lanes-are-used-by-the-pcie-card

PCI_ROOT_PATH = "/sys/bus/pci/devices/"


def _vram_amd(device) -> Optional[int]:
    ROOT_PATH = "/sys/bus/pci/devices/"
    vram_files = posixpath.join(*[ROOT_PATH, device, "drm", "card*", "device", "mem_info_vram_total"])
    try:
        drm_files = glob.glob(vram_files)
        if drm_files:
            with open(drm_files[0]) as f:
                vram_bits = int(f.read().strip())
                vram_mb = int(vram_bits / 1024 / 1024)
                return vram_mb
        return None
    except Exception:
        return None


def _pcie_gen(device) -> Optional[int]:
    # Path example: /sys/bus/pci/devices/0000:03:00.0/current_link_speed
    path = f"/sys/bus/pci/devices/{device}/current_link_speed"

    if not posixpath.exists(path):
        return None

    try:
        with open(path) as f:
            raw_speed = f.read().strip()  # e.g., "16.0 GT/s"

        # Mapping Dictionary
        speed_to_gen = {"2.5 GT/s": 1, "5.0 GT/s": 2, "8.0 GT/s": 3, "16.0 GT/s": 4, "32.0 GT/s": 5, "64.0 GT/s": 6}

        for k, v in speed_to_gen.items():
            """ `8.0 GT/s PCIe` may be a possible candidate, so we dont use direct matching"""
            if k in raw_speed:
                return v

        return None

    except Exception:
        return None


def _check_gpu_class(device: str) -> bool:
    path = posixpath.join(PCI_ROOT_PATH, device)
    with open(posixpath.join(path, "class")) as f:
        device_class = f.read().strip()
    """
    The class code is three hex-bytes, where the leftmost hex-byte is the base class
    We want the devices of base class 0x03, which denotes a Display Controller.
    """
    class_code = int(device_class, base=16)
    base_class = class_code >> 16

    return base_class == 3


def _populate_amd_info(gpu: GPUInfo, device: str) -> GPUInfo:
    # get VRAM for AMD GPUs
    vram_capacity = _vram_amd(device)
    if vram_capacity is not None:
        gpu.vram = Megabyte(capacity=vram_capacity)
    return gpu


def _populate_nvidia_info(gpu: GPUInfo, device: str) -> GPUInfo:
    gpu_name, pcie_width, pcie_gen, vram_total = fetch_gpu_details_nvidia(device)
    if gpu_name:
        gpu.name = gpu_name
    if pcie_width:
        gpu.pcie_width = pcie_width
    if pcie_gen:
        gpu.pcie_gen = pcie_gen
    if vram_total:
        gpu.vram = Megabyte(capacity=vram_total)

    return gpu


def _populate_lspci_info(gpu: GPUInfo, device: str) -> GPUInfo:
    lspci_output = subprocess.run(["lspci", "-s", device, "-vmm"], capture_output=True, text=True, check=True).stdout
    # We gather all data here and parse whatever data we have. Subsystem data may not be returned.
    # If LSPCI not found, check=True ensures error is thrown

    data = {}
    for line in lspci_output.splitlines():
        if ":" in line:
            key, value = line.split(":", maxsplit=1)
            data[key.strip()] = value.strip()

    gpu.manufacturer = data.get("Vendor")
    gpu.name = data.get("Device")
    gpu.subsystem_manufacturer = data.get("SVendor")
    gpu.subsystem_model = data.get("SDevice")

    return gpu


def fetch_graphics_info() -> GraphicsInfo:
    graphics_info = GraphicsInfo()

    if not posixpath.exists(PCI_ROOT_PATH):
        graphics_info.status.type = StatusType.FAILED
        graphics_info.status.messages.append("/sys/bus/pci/devices/ not found")
        return graphics_info

    for device in os.listdir(PCI_ROOT_PATH):
        # print("Found device: ", device)
        try:
            if not _check_gpu_class(device):
                continue
        except Exception as e:
            graphics_info.status.type = StatusType.PARTIAL
            graphics_info.status.messages.append(f"Could not open file for {device}: {e}")
            continue

        gpu = GPUInfo()
        gpu_path = posixpath.join(PCI_ROOT_PATH, device)

        try:
            with open(posixpath.join(gpu_path, "vendor")) as f:
                gpu.vendor_id = f.read().strip()
            with open(posixpath.join(gpu_path, "device")) as f:
                gpu.device_id = f.read().strip()
            with open(posixpath.join(gpu_path, "current_link_width")) as f:
                width = f.read().strip()
            if width.isnumeric() and int(width) > 0:
                gpu.pcie_width = int(width)
        except Exception as e:
            graphics_info.status.type = StatusType.PARTIAL
            graphics_info.status.messages.append(f"Could not get GPU properties: {e}")
        try:
            with open(posixpath.join(gpu_path, "firmware_node", "path")) as f:
                acpi_path = f.read().strip()
            gpu.acpi_path = acpi_path
        except Exception as e:
            graphics_info.status.type = StatusType.PARTIAL
            graphics_info.status.messages.append(f"Could not get ACPI path: {e}")
        try:
            pci_path = pci_path_linux(device)
            gpu.pci_path = pci_path
        except Exception as e:
            graphics_info.status.type = StatusType.PARTIAL
            graphics_info.status.messages.append(f"Could not get PCI path: {e}")

        if pcie_gen := _pcie_gen(device):
            gpu.pcie_gen = pcie_gen
        else:
            graphics_info.status.type = StatusType.PARTIAL
            graphics_info.status.messages.append("Could not get PCI gen")

        if gpu.vendor_id == "0x1002":
            gpu = _populate_amd_info(gpu, device)
        elif gpu.vendor_id and gpu.vendor_id.lower() == "0x10de":
            # get VRAM for Nvidia GPUs
            try:
                gpu = _populate_nvidia_info(gpu, device)
            except Exception as e:
                graphics_info.status.type = StatusType.PARTIAL
                graphics_info.status.messages.append(f"Could not get additional GPU info for NVIDIA GPU {device}: {e}")

        try:
            gpu = _populate_lspci_info(gpu, device)
        except Exception as e:
            graphics_info.status.type = StatusType.PARTIAL
            graphics_info.status.messages.append(f"Could not parse LSPCI output for GPU {device}: {e}")

        graphics_info.modules.append(gpu)

    return graphics_info
