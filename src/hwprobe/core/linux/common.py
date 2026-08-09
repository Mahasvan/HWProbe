# Source: https://github.com/KernelWanderers/OCSysInfo/blob/main/src/util/pci_root.py

import os
import posixpath
import re

_PCI_BDF_PATTERN = re.compile(r"^[0-9a-fA-F]{4}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}\.[0-7]$")


def pci_path_linux(device_slot: str):
    """
    :param device_slot: format: <domain>:<bus>:<slot>.<function>
    :return: PCI path, e.g. PciRoot(0x0)/Pci(0x2,0x0)
    """
    try:
        domain = int(device_slot.split(":")[0], 16)
    except (IndexError, ValueError):
        return None

    slots = _resolve_device_chain_from_sysfs(device_slot) or [device_slot]
    pci_components = [_format_pci_component(s) for s in slots]
    pci_suffix = "".join(f"/Pci({c})" for c in pci_components if c)
    return f"PciRoot({hex(domain)}){pci_suffix}"


def _format_pci_component(slot_name: str):
    """Return 'slot,func' as hex string, e.g. '0x1f,0x3', or None."""
    try:
        device_func = slot_name.split(":")[-1]
        slot, func = device_func.split(".")
        return f"{hex(int(slot, 16))},{hex(int(func, 16))}"
    except (ValueError, IndexError, AttributeError):
        return None


def _resolve_device_chain_from_sysfs(device_slot: str):
    """Return ordered PCI BDFs from root bridge to endpoint for a device."""
    sysfs_path = os.path.realpath(f"/sys/bus/pci/devices/{device_slot}")
    if not sysfs_path:
        return None

    bdfs = [p for p in sysfs_path.split(posixpath.sep) if _PCI_BDF_PATTERN.match(p)]
    if not bdfs:
        return None

    try:
        end = next(i for i, b in enumerate(bdfs) if b.lower() == device_slot.lower())
    except StopIteration:
        return None

    return bdfs[: end + 1]
