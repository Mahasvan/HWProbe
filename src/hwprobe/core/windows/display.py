from hwprobe.core.common.edid import parse_edid
from hwprobe.core.windows.win_enum import DISPLAY_CON_TYPE
from hwprobe.interops.win.bindings.display_info import (
    get_display_connectors,
    get_edid,
    get_gpu_for_display,
    get_monitor_devices,
)
from hwprobe.models.display_models import DisplayInfo, DisplayModuleInfo, ResolutionInfo
from hwprobe.models.status_models import StatusType


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
        module.acpi_path = dev.pnp_device_id
        module.resolution = ResolutionInfo(
            width=dev.width,
            height=dev.height,
            refresh_rate=float(dev.refresh_rate),
        )

        # GPU association via DXGI
        module.gpu_name = get_gpu_for_display(dev.device_id)

        # Connector type from CCD (more authoritative than EDID)
        connector = connectors.get(dev.device_id)
        if connector:
            module.interface = DISPLAY_CON_TYPE.get(connector.output_technology)

        # EDID — prefer display path for matching, fall back to PNP ID
        edid_key = (
            connector.display_path
            if connector and connector.display_path
            else dev.pnp_device_id.split("\\")[1]
            if "\\" in dev.pnp_device_id
            else dev.pnp_device_id
        )
        edid_bytes = get_edid(edid_key)
        if edid_bytes:
            module = _enrich_from_edid(module, edid_bytes)

        display_info.modules.append(module)

    if not display_info.modules:
        display_info.status.type = StatusType.FAILED

    return display_info
