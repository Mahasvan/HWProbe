import posixpath
import re
from typing import Optional

PCI_ROOT_PATH = "/sys/bus/pci/devices/"
_PCI_BDF_PATTERN = re.compile(r"^[0-9a-f]{4}:[0-9a-f]{2}:([0-9a-f]{2})\.([0-7])$", re.IGNORECASE)


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

    # Walk parent directories until an ACPI path is found or we hit filesystem root
    while (parent := posixpath.dirname(device_path)) != device_path:
        device_path = parent
        if acpi_path := _read_from_sysfs(device_path, "firmware_node", "path"):
            return acpi_path, False

    return ret_val


# Linux implemented this very annoyingly
# - https://tldp.org/LDP/tlk/dd/pci.html
# - https://wiki.osdev.org/PCI
def pci_path_linux(device_slot: str) -> Optional[str]:
    """
    :param device_slot: format: <domain>:<bus>:<device>.<function>
    :return: UEFI-style PCI path, e.g. PciRoot(0x0)/Pci(0x2,0x0)
    """
    # Invalid fallback value
    if not device_slot or not _PCI_BDF_PATTERN.match(device_slot):
        return None

    """
    Linux encodes the PCI bridge hierarchy directly in the resolved sysfs path:
        /sys/devices/pci0000:00/0000:00:03.1/0000:09:00.0

    Each <domain>:<bus>:<device>.<function> segment yields (device, function) via
    _PCI_BDF_PATTERN: [('03', '1'), ('00', '0')], which combined with the root domain
    from device_slot produces:
        PciRoot(0x0)/Pci(0x3,0x1)/Pci(0x0,0x0)
    """
    path = posixpath.realpath(posixpath.join(PCI_ROOT_PATH, device_slot))
    matches = [m for part in path.split(posixpath.sep) if (m := _PCI_BDF_PATTERN.match(part))]
    if not matches:
        return None

    domain = int(device_slot[:4], 16)
    segments = [f"Pci(0x{int(m[1], 16):x},0x{int(m[2], 16):x})" for m in matches]
    return f"PciRoot(0x{domain:x})/{'/'.join(segments)}"


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
