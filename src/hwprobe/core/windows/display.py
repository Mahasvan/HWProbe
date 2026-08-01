"""
Windows Display Information Module

All Win32 calls go through display_info.dll (C++). Python only does:
- EDID parsing (shared hwprobe.core.common.edid)
- Connector type mapping (DISPLAY_CON_TYPE from win_enum)
- Data assembly into DisplayModuleInfo
"""

from hwprobe.core.common.edid import parse_edid
from hwprobe.core.windows.common import format_acpi_path, format_pci_path
from hwprobe.core.windows.win_enum import DISPLAY_CON_TYPE
from hwprobe.interops.win.bindings.display_info import (
    get_display_connectors,
    get_edid,
    get_gpu_for_display,
    get_monitor_devices,
)
from hwprobe.models.display_models import DisplayInfo, DisplayModuleInfo, ResolutionInfo
from hwprobe.models.status_models import StatusType
from hwprobe.util.location_paths import get_location_paths


def _enrich_from_edid(module: DisplayModuleInfo, edid_bytes: bytes) -> DisplayModuleInfo:
    """Fill in gaps on a DisplayModuleInfo from parsed EDID data.

    Only sets fields that are currently None — existing values win.
    Resolution fields are merged individually.
    """
    data = parse_edid(edid_bytes)

    for field in data.model_dump().keys():
        if field == "resolution":
            continue
        if getattr(module, field) is None:
            setattr(module, field, getattr(data, field))

    if data.resolution is None:
        return module
    if module.resolution is None:
        module.resolution = data.resolution
        return module
    for field in data.resolution.model_dump():
        if getattr(module.resolution, field) is None:
            setattr(module.resolution, field, getattr(data.resolution, field))

    return module


def fetch_display_info() -> DisplayInfo:
    display_info = DisplayInfo()

    # Connector info from CCD API (display paths + output technology)
    try:
        connectors = {c.display_id: c for c in get_display_connectors()}
    except RuntimeError:
        connectors = {}
        display_info.status.type = StatusType.PARTIAL
        display_info.status.messages.append("Failed to fetch display connector information")

    for dev in get_monitor_devices():
        module = DisplayModuleInfo()
        module.resolution = ResolutionInfo(
            width=dev.width,
            height=dev.height,
            refresh_rate=float(dev.refresh_rate),
        )

        # Location paths from PNP device ID (same as graphics.py and network.py)
        loc = get_location_paths(dev.pnp_device_id)
        if loc is not None:
            pci, acpi = loc[:2]
            module.pci_path = format_pci_path(pci)
            module.acpi_path = format_acpi_path(acpi)

        # GPU association via DXGI
        module.gpu_name = get_gpu_for_display(dev.device_id)

        # Connector type from CCD (more authoritative than EDID)
        connector = connectors.get(dev.device_id)
        if connector:
            module.interface = DISPLAY_CON_TYPE.get(connector.output_technology)

        # EDID — try display path first, fall back to PNP ID segment
        edid_bytes = None
        if connector and connector.display_path:
            edid_bytes = get_edid(connector.display_path)
        if not edid_bytes and "\\" in dev.pnp_device_id:
            edid_bytes = get_edid(dev.pnp_device_id.split("\\")[1])
        if edid_bytes:
            module = _enrich_from_edid(module, edid_bytes)

        display_info.modules.append(module)

    if not display_info.modules:
        display_info.status.type = StatusType.FAILED

    return display_info
