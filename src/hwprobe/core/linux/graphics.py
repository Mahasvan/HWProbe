import glob
import os
import subprocess
from typing import Optional

from hwprobe.core.common.pci_ids import lookup as pci_ids_lookup
from hwprobe.core.linux.common import pci_path_linux
from hwprobe.models.gpu_models import GPUInfo, GraphicsInfo
from hwprobe.models.size_models import Megabyte
from hwprobe.models.status_models import StatusType
from hwprobe.util.nvidia import fetch_gpu_details_nvidia

# Try to import native C library bindings
try:
    from hwprobe.interops.linux.bindings import gpu_info as native_gpu

    NATIVE_AVAILABLE = native_gpu.is_available()
except (ImportError, RuntimeError) as e:
    NATIVE_AVAILABLE = False

# Currently, the info in /sys/class/drm/cardX is being used.
# todo: Check if lspci and lshw -c display can be used
# https://unix.stackexchange.com/questions/393/how-to-check-how-many-lanes-are-used-by-the-pcie-card

PCI_ROOT_PATH = "/sys/bus/pci/devices/"
DISPLAY_CONTROLLER_CLASS = 0x03  # Display Controller class code in PCI


def _vram_amd(device) -> Optional[int]:
    ROOT_PATH = "/sys/bus/pci/devices/"
    vram_files = os.path.join(*[ROOT_PATH, device, "drm", "card*", "device", "mem_info_vram_total"])
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
    # Path example: /sys/bus/pci/devices/0000:03:00.0/max_link_speed
    path = f"/sys/bus/pci/devices/{device}/max_link_speed"

    if not os.path.exists(path):
        return None

    try:
        with open(path) as f:
            raw_speed = f.read().strip()  # e.g., "16.0 GT/s"

        print("Raw PCIe speed string:", raw_speed)  # Debugging output

        # Mapping Dictionary
        speed_to_gen = {"2.5 GT/s": 1, "5.0 GT/s": 2, "8.0 GT/s": 3, "16.0 GT/s": 4, "32.0 GT/s": 5, "64.0 GT/s": 6}

        for k, v in speed_to_gen.items():
            """ `8.0 GT/s PCIe` may be a possible candidate, so we dont use direct matching"""
            if k in raw_speed:
                print("Matched PCIe speed:", k, "-> Gen", v)  # Debugging output
                return v

        return None

    except Exception:
        return None


def _check_gpu_class(device: str) -> bool:
    path = os.path.join(PCI_ROOT_PATH, device)
    with open(os.path.join(path, "class")) as f:
        device_class = f.read().strip()
    """
    The class code is three hex-bytes, where the leftmost hex-byte is the base class
    We want the devices of base class 0x03, which denotes a Display Controller.
    """
    class_code = int(device_class, base=16)
    base_class = class_code >> 16

    return base_class == DISPLAY_CONTROLLER_CLASS


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


def _populate_pci_ids_info(gpu: GPUInfo, device: str) -> bool:
    """
    Resolve GPU vendor/device/subsystem names from the local pci.ids database.

    This avoids spawning an `lspci` subprocess for the common case. Returns
    True if useful names were found; False means the caller should fall back
    to `_populate_lspci_info`.
    """
    if not gpu.vendor_id or not gpu.device_id:
        return False

    subvendor_id: Optional[str] = None
    subdevice_id: Optional[str] = None
    try:
        with open(os.path.join(PCI_ROOT_PATH, device, "subsystem_vendor")) as f:
            subvendor_id = f.read().strip()
        with open(os.path.join(PCI_ROOT_PATH, device, "subsystem_device")) as f:
            subdevice_id = f.read().strip()
    except Exception:
        pass  # Subsystem info is optional

    try:
        result = pci_ids_lookup(gpu.vendor_id, gpu.device_id, subvendor_id, subdevice_id)
    except Exception:
        return False

    if not result.vendor_name or not result.device_name:
        return False

    gpu.manufacturer = result.vendor_name
    if not gpu.name:
        gpu.name = result.device_name

    if subvendor_id and subdevice_id and result.subsystem_name:
        try:
            # A bogus device_id is fine here; we only need the subvendor's name.
            gpu.subsystem_manufacturer = pci_ids_lookup(subvendor_id, "0000").vendor_name
        except Exception:
            pass
        gpu.subsystem_model = result.subsystem_name

    return True


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
    """
    Fetch GPU information on Linux.
    
    Priority:
    1. Native C library (libdevice_info.so) - covers all vendors via DRM + Vulkan
    2. Fallback to Python-based sysfs + lspci parsing
    """
    graphics_info = GraphicsInfo()

    # Try native library first (preferred path)
    if NATIVE_AVAILABLE:
        try:
            native_gpus = native_gpu.get_gpu_info()
            for ng in native_gpus:
                gpu = GPUInfo()
                
                # Basic identification
                gpu.vendor_id = f"0x{ng.vendor_id:04x}"
                gpu.device_id = f"0x{ng.device_id:04x}"
                gpu.name = ng.name if ng.name else None
                
                # PCIe info
                if ng.pcie_gen > 0:
                    gpu.pcie_gen = ng.pcie_gen
                if ng.pcie_width > 0:
                    gpu.pcie_width = ng.pcie_width
                
                # VRAM
                if ng.vram_total_mb > 0:
                    gpu.vram = Megabyte(capacity=ng.vram_total_mb)
                
                # PCI slot (BDF address like 0000:01:00.0)
                if ng.pci_slot:
                    # Store it as-is; could be used for PCI path construction if needed
                    pass
                
                # Try to get additional info via local pci.ids DB (fast path) or lspci (fallback)
                if ng.pci_slot:
                    try:
                        if not _populate_pci_ids_info(gpu, ng.pci_slot):
                            gpu = _populate_lspci_info(gpu, ng.pci_slot)
                    except Exception as e:
                        graphics_info.status.type = StatusType.PARTIAL
                        graphics_info.status.messages.append(
                            f"Could not parse LSPCI output for GPU {ng.pci_slot}: {e}"
                        )
                
                # Try to get PCI/ACPI paths from sysfs
                sysfs_device_path = os.path.join(PCI_ROOT_PATH, ng.pci_slot)
                if os.path.exists(sysfs_device_path):
                    try:
                        with open(os.path.join(sysfs_device_path, "firmware_node", "path")) as f:
                            gpu.acpi_path = f.read().strip()
                    except Exception:
                        pass  # ACPI path is optional
                    
                    try:
                        gpu.pci_path = pci_path_linux(ng.pci_slot)
                    except Exception:
                        pass  # PCI path is optional
                
                graphics_info.modules.append(gpu)
            
            return graphics_info
            
        except Exception as e:
            # Native library failed, fall back to Python implementation
            graphics_info.status.type = StatusType.PARTIAL
            graphics_info.status.messages.append(f"Native library failed, using fallback: {e}")
            # Continue to fallback below

    # Fallback: Python-based implementation
    if not os.path.exists(PCI_ROOT_PATH):
        graphics_info.status.type = StatusType.FAILED
        graphics_info.status.messages.append("/sys/bus/pci/devices/ not found")
        return graphics_info

    for device in os.listdir(PCI_ROOT_PATH):
        try:
            if not _check_gpu_class(device):
                continue
        except Exception as e:
            graphics_info.status.type = StatusType.PARTIAL
            graphics_info.status.messages.append(f"Could not open file for {device}: {e}")
            continue

        print("Found device: ", device)
        gpu = GPUInfo()
        gpu_path = os.path.join(PCI_ROOT_PATH, device)

        try:
            with open(os.path.join(gpu_path, "vendor")) as f:
                gpu.vendor_id = f.read().strip()
            with open(os.path.join(gpu_path, "device")) as f:
                gpu.device_id = f.read().strip()
            with open(os.path.join(gpu_path, "max_link_width")) as f:
                width = f.read().strip()
            if width.isnumeric() and int(width) > 0:
                gpu.pcie_width = int(width)
        except Exception as e:
            graphics_info.status.type = StatusType.PARTIAL
            graphics_info.status.messages.append(f"Could not get GPU properties: {e}")
        try:
            with open(os.path.join(gpu_path, "firmware_node", "path")) as f:
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
            if not _populate_pci_ids_info(gpu, device):
                gpu = _populate_lspci_info(gpu, device)
        except Exception as e:
            graphics_info.status.type = StatusType.PARTIAL
            graphics_info.status.messages.append(f"Could not parse LSPCI output for GPU {device}: {e}")

        graphics_info.modules.append(gpu)

    return graphics_info
