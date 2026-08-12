# Source: https://github.com/KernelWanderers/OCSysInfo/blob/main/src/util/pci_root.py

import posixpath
import re
from typing import Optional
from pathlib import Path

_PCI_BDF_PATTERN = re.compile(r"^[0-9a-fA-F]{4}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}\.[0-7]$")


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
