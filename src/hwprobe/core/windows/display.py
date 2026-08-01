"""
Windows Display Information Module

All Win32 calls go through display_info.dll (C++). Python only does:
- EDID parsing (shared hwprobe.core.common.edid)
- Connector type mapping (DISPLAY_CON_TYPE from win_enum)
- Data assembly into DisplayModuleInfo

Monitor name priority: EDID 0xFC descriptor → CCD monitorFriendlyName → None
"""

from hwprobe.core.common.edid import parse_edid
from hwprobe.core.windows.common import format_acpi_path, format_pci_path
from hwprobe.core.windows.win_enum import DISPLAY_CON_TYPE
from hwprobe.interops.win.bindings.display_info import get_display_devices, get_edid
from hwprobe.models.display_models import DisplayInfo, DisplayModuleInfo, ResolutionInfo
from hwprobe.models.status_models import StatusType
from hwprobe.util.location_paths import get_location_paths


def _enrich_from_edid(module: DisplayModuleInfo, edid_bytes: bytes) -> None:
    """Fill None fields on module from parsed EDID. Existing values win."""
    data = parse_edid(edid_bytes)

    if module.name is None:
        module.name = data.name
    if module.manufacturer_code is None:
        module.manufacturer_code = data.manufacturer_code
    if module.year is None:
        module.year = data.year
    if module.serial_number is None:
        module.serial_number = data.serial_number
    if module.interface is None:
        module.interface = data.interface

    if data.resolution is None:
        return
    if module.resolution is None:
        module.resolution = data.resolution
        return
    for field in data.resolution.model_dump():
        if getattr(module.resolution, field) is None:
            setattr(module.resolution, field, getattr(data.resolution, field))


def fetch_display_info() -> DisplayInfo:
    display_info = DisplayInfo()

    for dev in get_display_devices():
        module = DisplayModuleInfo()
        module.resolution = ResolutionInfo(
            width=dev.width,
            height=dev.height,
            refresh_rate=float(dev.refresh_rate),
        )
        module.gpu_name = dev.gpu_name or None
        module.interface = DISPLAY_CON_TYPE.get(dev.output_technology)

        # Location paths from PNP device ID
        loc = get_location_paths(dev.pnp_device_id)
        if loc is not None:
            module.pci_path = format_pci_path(loc[0])
            module.acpi_path = format_acpi_path(loc[1])

        # EDID — try display path first, fall back to PNP ID segment
        edid_bytes = get_edid(dev.display_path) if dev.display_path else None
        if not edid_bytes and "\\" in dev.pnp_device_id:
            edid_bytes = get_edid(dev.pnp_device_id.split("\\")[1])
        if edid_bytes:
            _enrich_from_edid(module, edid_bytes)

        # CCD monitorFriendlyName — fallback only, EDID name wins
        if module.name is None and dev.monitor_name:
            module.name = dev.monitor_name

        display_info.modules.append(module)

    if not display_info.modules:
        display_info.status.type = StatusType.FAILED

    return display_info
