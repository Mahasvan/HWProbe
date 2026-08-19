import posixpath
import re
from typing import Optional

PCI_ROOT_PATH = "/sys/bus/pci/devices/"
_PCI_BDF_PATTERN = re.compile(r"^[0-9a-fA-F]{4}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}\.[0-7]$")
_PCI_BDF_PATH_PATTERN = re.compile(r"(pci([a-f\d]{4}):([a-f\d]{2}))|(([a-f\d]{4}):([a-f\d]{2}):([a-f\d]{2})\.([a-f\d]{1}))", re.IGNORECASE)

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
def pci_path_linux(device_slot: str) -> Optional[str]:
    """
    :param device_slot: format: <domain>:<bus>:<device>.<function>
    :return: UEFI-style PCI path, e.g. PciRoot(0x0)/Pci(0x2,0x0)
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

    r"""
    On Linux, PCI devices are described directly in their sysfs path structure.
    I.e: /sys/devices/<PCIROOT>/<PCI_DEVICE>/<PCI_DEVICE>/...

    We are trying to extract the PCI root value, and the PCI function segments from this path.
    This is done by finding all matches of the PCI BDF PATH PATTERN in the path,
    and using the match groups to determine if it's a root or segment path.

    The base regex contains two distinct capture groups:
            pci([0-9a-fA-F]{4}):([0-9a-fA-F]{2}))
            ([0-9a-fA-F]{4}):([0-9a-fA-F]{2}):([0-9a-fA-F]{2})\.([0-9a-fA-F]{1}))

    This will then allow us to determine if a match is a root or segment path
    by checking match[0], if it's an empty string: it's a segment path, otherwise it's a root path.

    Given a path: '/sys/devices/pci0000:00/0000:00:03.1/0000:09:00.0'

    This would make the PCI hierarchy: PciRoot(0x0)/Pci(0x3,0x1)/Pci(0x0,0x0)

    Then, when matching, we'd get a result like so:
    matches = [
        ('pci0000:00', '0000', '00', '', '', '', '', ''),
        ('', '', '', '0000:00:03.1', '0000', '00', '03', '1'),
        ('', '', '', '0000:09:00.0', '0000', '09', '00', '0')P
    ]

    Structure of a single match:

                         PCI Root                      PCI function (segment)
                   _ _ _ _ _|_ _ _ _ _             _ _ _ _ _ _ _ | _ _ _ _ _ _ _
                  |         |         |           |          |       |     |    |
        (   'pciXXXX:YY', 'XXXX',   'YY',  'XXXX:YY:ZZ.F', 'XXXX', 'YY', 'ZZ', 'F'   )
    """
    matches = _PCI_BDF_PATH_PATTERN.findall(path)
    for match in matches:
        if not match:
            continue

        if match[0]:
            pci_root = f"PciRoot(0x{int(match[1], 16):x})"
        elif match[4]:
            pci_segments.append(f"Pci(0x{int(match[6], 16):x},0x{int(match[7], 16):x})")

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
