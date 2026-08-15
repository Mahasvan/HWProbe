import posixpath
import re
from typing import Optional
from pathlib import Path
from enum import Enum

PCI_ROOT_PATH = "/sys/bus/pci/devices/"
_PCI_BDF_PATTERN = re.compile(r"^[0-9a-fA-F]{4}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}\.[0-7]$")

def _resolve_acpi_path(device_bdf: str) -> tuple[Optional[str], bool]:
    """
    Resolve the ACPI path for a given PCI device.

    :param device_bdf: The BDF identifier (Bus:Device.Function) of the device

    :return: The resolved ACPI path if found, else None.
    
    The way this function works is:
    1. It first checks if the device has a direct ACPI path in its sysfs entry.
    2. If not, it checks the parent devices recursively until it finds an ACPI path or reaches the root.
    """
    ret_val = None, False
    device_path = posixpath.join(PCI_ROOT_PATH, device_bdf)
    if not posixpath.exists(device_path):
        return ret_val

    acpi_path = _read_from_sysfs(device_path, "firmware_node", "path")
    if acpi_path:
        return acpi_path, True
    
    device_path = posixpath.realpath(device_path)
    
    # Parent directory should be something like RRRR:BB:DD.F
    try:
        while (acpi_path := _read_from_sysfs(device_path, "firmware_node", "path")) is None:
            if device_path == posixpath.dirname(device_path):
                # We've reached the root of the filesystem without finding an ACPI path
                return ret_val
            
            device_path = posixpath.dirname(device_path)
            
    except Exception:
        return ret_val
    
    # Device has no ACPI path, it is found via PCI enumeration
    # Return parent ACPI path instead.
    return acpi_path, False


# Linux implemented this very annoyingly
# - https://tldp.org/LDP/tlk/dd/pci.html
# - https://wiki.osdev.org/PCI
def pci_path_linux(device_slot: str):
    """
    :param device_slot: format: <domain>:<bus>:<device>.<function>
    :return: PCI path, e.g. PciRoot(0x0)/Pci(0x2,0x0)
    """
    # Invalid fallback value
    if not device_slot or not _PCI_BDF_PATTERN.match(device_slot):
        return None
    
    raw_path = f"/sys/bus/pci/devices/{device_slot}/"

    path = posixpath.realpath(raw_path)
    if not path:
        return None
    
    pci_root = ""
    pci_segments = []
    
    for part in path.split(posixpath.sep):
        """
        The way Linux represents PCI devices in sysfs is according to their BDF (Bus:Device.Function) notation. 
        The root bridge is represented as "pci<RRRR>:<BB>", and each subsequent device is represented as "<RRRR>:<BB>:<DD>.<F>".
        """
        
        if part.startswith("pci"):
            try:
                root_bus = part.split(":")[0].split("pci")[-1]
                pci_root = f"PciRoot(0x{int(root_bus, 16):x})"
            except (ValueError, IndexError):
                return None
            
        elif ":" in part and "." in part: # Only the root bridge does not contain a function number
            try:
                bdf_segments = part.split(":")[-1]
                dev, func = bdf_segments.split(".")
                
                pci_segments.append(f"Pci(0x{int(dev, 16):x},0x{int(func, 16):x})")
            except (ValueError, IndexError) as e:
                print(f"Error parsing PCI device/function from {part}: {e}")
                return None

    if not pci_root or not pci_segments:
        return None

    return f"{pci_root}/{'/'.join(pci_segments)}"
    

def _read_from_sysfs(base: str, *paths) -> Optional[str]:
    """Read a string from a sysfs file, return None if not found."""
    path = posixpath.join(base, *paths)

    if not posixpath.exists(path):
        return None
    
    try:
        with open(path) as f:
            return f.read().strip()
    except Exception:
        return None
