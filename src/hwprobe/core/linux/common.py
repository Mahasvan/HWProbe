# Source: https://github.com/KernelWanderers/OCSysInfo/blob/main/src/util/pci_root.py

import posixpath
import re
from typing import Optional
from pathlib import Path
from enum import Enum

PCI_ROOT_PATH = "/sys/bus/pci/devices/"
_PCI_BDF_PATTERN = re.compile(r"^[0-9a-fA-F]{4}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}\.[0-7]$")

class ACPIResult(Enum):
    SUCCESS = 0
    INFERRED = 1
    FAILURE = 2

def _resolve_acpi_path(device_bdf: str) -> tuple[Optional[str], ACPIResult]:
    """
    Resolve the ACPI path for a given PCI device.

    :param device_bdf: The BDF identifier (Bus:Device.Function) of the device

    :return: The resolved ACPI path if found, else None.
    
    The way this function works is:
    1. It first checks if the device has a direct ACPI path in its sysfs entry.
    2. If not, it checks the parent devices recursively until it finds an ACPI path or reaches the root.
    """
    ret_val = (None, ACPIResult.FAILURE)
    device_path = os.path.join(PCI_ROOT_PATH, device_bdf)
    dev, func = device_bdf.split(":")[-1].split(".")
    if not os.path.exists(device_path):
        return ret_val

    acpi_path = _read_from_sysfs(device_path, "firmware_node", "path")
    if acpi_path:
        return acpi_path, ACPIResult.SUCCESS
    
    device_path = os.path.realpath(device_path)
    
    # Parent directory should be something like RRRR:BB:DD.F
    try:
        while (acpi_path := _read_from_sysfs(device_path, "firmware_node", "path")) is None:
            print(device_path)
            device_path = os.path.dirname(device_path)
            
    except Exception:
        return ret_val
    
    print(acpi_path)
    
    return acpi_path, ACPIResult.INFERRED


# Linux implemented this very annoyingly
# - https://tldp.org/LDP/tlk/dd/pci.html
# - https://wiki.osdev.org/PCI
def pci_path_linux(device_slot: str):
    """
    :param device_slot: format: <domain>:<bus>:<device>.<function>
    :return: PCI path, e.g. PciRoot(0x0)/Pci(0x2,0x0)
    """
    # Invalid fallback value
    def_val = "PciRoot(0x0)/Pci(0x0,0x0)" 
    if not device_slot or not _PCI_BDF_PATTERN.match(device_slot):
        return None
    
    raw_path = f"/sys/bus/pci/devices/{device_slot}/"

    path = os.path.realpath(raw_path)
    if not path:
        return None
    
    pci_root = ""
    pci_segments = []
    
    for part in path.split(os.sep):
        if part.startswith("pci"):
            try:
                root_bus = part.split(":")[0].split("pci")[-1]
                pci_root = f"PciRoot(0x{int(root_bus, 16):x})"
            except (ValueError, IndexError) as e:
                print(f"Error parsing PCI root bus from {part}: {e}")
                return def_val
            
        elif ":" in part and "." in part: # Only the root bridge does not contain a function number
            try:
                bdf_segments = part.split(":")[-1]
                dev, func = bdf_segments.split(".")
                
                pci_segments.append(f"Pci(0x{int(dev, 16):x},0x{int(func, 16):x})")
            except (ValueError, IndexError) as e:
                print(f"Error parsing PCI device/function from {part}: {e}")
                return def_val

    if not pci_root or not pci_segments:
        return def_val

    return f"{pci_root}/{'/'.join(pci_segments)}"
    

def _read_from_sysfs(base: str, *paths) -> Optional[str]:
    """Read a string from a sysfs file, return None if not found."""
    path = os.path.join(base, *paths)
    
    if not os.path.exists(path):
        return None
    
    try:
        with open(path) as f:
            return f.read().strip()
    except Exception:
        return None
