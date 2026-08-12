from hwprobe.core.windows.common import format_acpi_path, format_pci_path
from hwprobe.interops.win.bindings.wmi import get_wmi_data
from hwprobe.models.network_models import NetworkInfo, NICInfo
from hwprobe.models.status_models import Status, StatusType
from hwprobe.util.location_paths import get_location_paths


def fetch_network_info_fast() -> NetworkInfo:
    network_info = NetworkInfo(status=Status(type=StatusType.SUCCESS))

    # MSFT_NetAdapter is present in Windows 8 and above.
    try:
        rows = get_wmi_data(
            "MSFT_NetAdapter", ["InterfaceDescription", "PNPDeviceID", "Virtual"], namespace="root/StandardCimv2"
        )
    except RuntimeError as e:
        network_info.status.type = StatusType.FAILED
        network_info.status.messages.append(str(e))
        return network_info

    if not rows:
        network_info.status.type = StatusType.FAILED
        network_info.status.messages.append("Network adapter query returned no data")
        return network_info

    visited_device_ids = set()

    for row in rows:
        # Skip loopback adapters
        if row.get("Virtual", "") != "0":
            # Booleans are represented a "0" and "-1".
            # if Virtual is -1, then it is not a physical adapter.
            continue

        pnp_device_id = row.get("PNPDeviceID", "").strip()

        # Deduplicate entries based on PnP Device ID - Wifi devices get enumerated multiple times
        if pnp_device_id in visited_device_ids: continue
        visited_device_ids.add(pnp_device_id)

        name = row.get("InterfaceDescription", "").strip()

        if not pnp_device_id or not name:
            network_info.status.type = StatusType.PARTIAL
            network_info.status.messages.append("Missing PNPDeviceID for network interface; skipping")
            continue

        # Skip virtual/software adapters (ROOT\ prefix = software-enumerated)
        upper_pnp = pnp_device_id.upper()
        if upper_pnp.startswith("ROOT\\"):
            continue

        module = NICInfo()

        if "VEN_" in upper_pnp and "DEV_" in upper_pnp:
            module.vendor_id = pnp_device_id.split("VEN_")[1][:4]
            module.device_id = pnp_device_id.split("DEV_")[1][:4]
        elif "VID_" in upper_pnp and "PID_" in upper_pnp:
            module.vendor_id = pnp_device_id.split("VID_")[1][:4]
            module.device_id = pnp_device_id.split("PID_")[1][:4]
        else:
            network_info.status.type = StatusType.PARTIAL
            network_info.status.messages.append(f"Could not parse Vendor/Device ID from PNPDeviceID: {pnp_device_id}")

        loc = get_location_paths(pnp_device_id)
        if loc and len(loc) >= 2:
            pci, acpi = loc[:2]
            module.pci_path = format_pci_path(pci)
            module.acpi_path = format_acpi_path(acpi)
        else:
            network_info.status.type = StatusType.PARTIAL
            network_info.status.messages.append(
                f"Could not determine location paths for NIC with PNPDeviceID: {pnp_device_id}"
            )

        # todo: Populate module.manufacturer once pci-ids parsing is implemented
        module.name = name
        network_info.modules.append(module)

    return network_info
