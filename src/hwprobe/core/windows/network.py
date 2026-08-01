import ctypes

from hwprobe.core.windows.common import format_acpi_path, format_pci_path

# todo: refactor to new bindings
from hwprobe.interops.win.legacy.constants import STATUS_OK
from hwprobe.interops.win.legacy.signatures import GetNetworkHardwareInfo
from hwprobe.models.network_models import NetworkInfo, NICInfo
from hwprobe.models.status_models import Status, StatusType
from hwprobe.util.location_paths import get_location_paths


def fetch_network_info_fast() -> NetworkInfo:
    network_info = NetworkInfo(status=Status(type=StatusType.SUCCESS))

    # 256 bytes per property, 3 properties, 5 modules
    buf_size = 256 * 3 * 5
    raw_data = ctypes.create_string_buffer(buf_size)

    res = GetNetworkHardwareInfo(raw_data, buf_size)

    # the method couldn't execute successfully
    if res != STATUS_OK:
        network_info.status.type = StatusType.FAILED
        network_info.status.messages.append(f"Network HW info query failed with status code: {res}")
        return network_info

    decoded = raw_data.value.decode("utf-8", errors="ignore").strip()

    # data is empty
    if not decoded:
        network_info.status.type = StatusType.FAILED
        network_info.status.messages.append("Network HW info query returned no data")
        return network_info

    for line in decoded.split("\n"):
        if not line or "|" not in line:
            continue

        parsed = dict(x.split("=", 1) for x in line.split("|") if "=" in x)

        module = NICInfo()
        pnp_device_id = parsed.get("PNPDeviceID", None)
        manufacturer = parsed.get("Manufacturer", None)
        name = parsed.get("Name", None)

        if not pnp_device_id or not manufacturer or not name:
            network_info.status.type = StatusType.PARTIAL
            network_info.status.messages.append("Missing PNPDeviceID for network interface; skipping")
            continue

        if "VEN_" in pnp_device_id and "DEV_" in pnp_device_id:
            module.vendor_id = pnp_device_id.split("VEN_")[1][:4]
            module.device_id = pnp_device_id.split("DEV_")[1][:4]
        elif "VID_" in pnp_device_id and "PID_" in pnp_device_id:
            module.vendor_id = pnp_device_id.split("VID_")[1][:4]
            module.device_id = pnp_device_id.split("PID_")[1][:4]
        else:
            network_info.status.type = StatusType.PARTIAL
            network_info.status.messages.append(f"Could not parse Vendor/Device ID from PNPDeviceID: {pnp_device_id}")

        loc = get_location_paths(pnp_device_id)

        if loc is not None:
            pci, acpi = loc[:2]

            module.pci_path = format_pci_path(pci)
            module.acpi_path = format_acpi_path(acpi)
        else:
            network_info.status.type = StatusType.PARTIAL
            network_info.status.messages.append(
                f"Could not determine location paths for NIC with PNPDeviceID: {pnp_device_id}"
            )

        module.manufacturer = manufacturer.strip()
        module.name = name.strip()
        network_info.modules.append(module)

    return network_info
