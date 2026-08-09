import os
import re
from typing import Callable, Optional

from hwprobe.core.common.edid import INTERFACE_ENUM, parse_edid
from hwprobe.core.common.pci_ids import PCILookupResult
from hwprobe.core.linux.common import pci_path_linux
from hwprobe.models.display_models import DisplayInfo, DisplayModuleInfo
from hwprobe.models.status_models import StatusType

_PCI_BDF_PATTERN = re.compile(r"^[0-9a-fA-F]{4}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}\.[0-7]$")

DRM_CONNECTOR_TYPE = {
    "eDP": INTERFACE_ENUM[5],  # DisplayPort
    "DP": INTERFACE_ENUM[5],  # DisplayPort
    "HDMI-A": INTERFACE_ENUM[2],  # HDMI
    "HDMI-B": INTERFACE_ENUM[3],  # HDMI (B)
    "DVI-D": INTERFACE_ENUM[1],  # DVI
    "DVI-I": INTERFACE_ENUM[1],  # DVI
    "DVI-A": INTERFACE_ENUM[1],  # DVI
    "VGA": "Analog",
    "LVDS": "LVDS",
    "DSI": "DSI",
}


def _extract_pci_bdf_from_sysfs_path(path: str) -> Optional[str]:
    """Extract the endpoint PCI BDF from a resolved sysfs path."""
    parts = [part for part in path.strip().split(os.path.sep) if part]
    bdf_candidates = [part for part in parts if _PCI_BDF_PATTERN.match(part)]
    return bdf_candidates[-1] if bdf_candidates else None


def _parse_connector_type(device_path: str) -> Optional[str]:
    """Extract interface type from a DRM connector directory name like card0-HDMI-A-1."""
    basename = os.path.basename(device_path)
    m = re.match(r"card\d+-(.+)-\d+$", basename)
    if not m:
        return None
    return DRM_CONNECTOR_TYPE.get(m.group(1))


def _fetch_individual_monitor_info(
    device_path: str,
    pci_lookup: Optional[Callable[[str, str], PCILookupResult]] = None,
) -> Optional[DisplayModuleInfo]:
    edid_path = os.path.join(device_path, "edid")
    if not os.path.exists(edid_path):
        return None

    # For some reason, it's not guaranteed to only have a single "device" directory in the tree/chain
    # So, we look at how many is necessary until "device" stops being a directory.
    parent_path = device_path

    while os.path.exists(t := os.path.join(parent_path, "device")) and os.path.isdir(t):
        parent_path = t

    with open(edid_path, "rb") as f:
        edid_data = f.read()
    if len(edid_data) == 0:
        return None

    monitor_data = parse_edid(edid_data)

    if connector_type := _parse_connector_type(device_path):
        monitor_data.interface = connector_type

    pci_path_full = os.path.realpath(parent_path)
    pci_bdf = _extract_pci_bdf_from_sysfs_path(pci_path_full)
    if pci_bdf:
        monitor_data.pci_path = pci_path_linux(pci_bdf)

    # Resolve parent GPU name via PCI-IDS
    if pci_lookup and os.path.isdir(parent_path):
        vendor_file = os.path.join(parent_path, "vendor")
        device_file = os.path.join(parent_path, "device")
        if os.path.exists(vendor_file) and os.path.exists(device_file):
            with open(vendor_file) as f:
                vendor_id = f.read().strip()
            with open(device_file) as f:
                device_id = f.read().strip()
            result = pci_lookup(vendor_id, device_id)
            if result.device_name:
                monitor_data.gpu_name = result.device_name

    acpi_file = os.path.join(device_path, "firmware_node", "path")
    if os.path.exists(acpi_file):
        with open(acpi_file) as f:
            monitor_data.acpi_path = f.read().strip()

    return monitor_data


def fetch_display_info(
    pci_lookup: Optional[Callable[[str, str], PCILookupResult]] = None,
):
    display_info = DisplayInfo()
    pattern = re.compile(r"^card\d+$")
    root_path = "/sys/class/drm"

    if not os.path.isdir(root_path):
        display_info.status.type = StatusType.FAILED
        display_info.status.messages.append("/sys/class/drm not found")
        return display_info

    parent_devices = os.listdir(root_path)
    parent_devices = [os.path.join(root_path, device) for device in parent_devices if pattern.match(device)]

    for parent_path in parent_devices:
        children = [x for x in os.listdir(parent_path) if x.startswith("card")]
        for child in children:
            try:
                response = _fetch_individual_monitor_info(os.path.join(parent_path, child), pci_lookup)
                if response:
                    display_info.modules.append(response)
            except Exception as e:
                display_info.status.type = StatusType.PARTIAL
                display_info.status.messages.append(f"Display Info ({child}): {e!s}")

    return display_info
