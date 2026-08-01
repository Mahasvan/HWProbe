from hwprobe.core.windows.common import format_acpi_path, format_pci_path
from hwprobe.interops.win.bindings.wmi import get_wmi_data
from hwprobe.models.network_models import NetworkInfo, NICInfo
from hwprobe.models.status_models import Status, StatusType
from hwprobe.util.location_paths import get_location_paths


def fetch_network_info_fast() -> NetworkInfo:
    network_info = NetworkInfo(status=Status(type=StatusType.SUCCESS))

    try:
        rows = get_wmi_data(
            "Win32_NetworkAdapter",
            ["Name", "Manufacturer", "PNPDeviceID", "AdapterType"],
        )
    except RuntimeError as e:
        network_info.status.type = StatusType.FAILED
        network_info.status.messages.append(str(e))
        return network_info

    if not rows:
        network_info.status.type = StatusType.FAILED
        network_info.status.messages.append("Network adapter query returned no data")
        return network_info

    for row in rows:
        # Skip loopback adapters
        if "Loopback Interface" in row.get("AdapterType", "").strip():
            continue

        pnp_device_id = row.get("PNPDeviceID", "").strip()
        manufacturer = row.get("Manufacturer", "").strip()
        name = row.get("Name", "").strip()

        if not pnp_device_id or not manufacturer or not name:
            network_info.status.type = StatusType.PARTIAL
            network_info.status.messages.append("Missing PNPDeviceID for network interface; skipping")
            continue

        # Only physical PCI and USB NICs
        upper_pnp = pnp_device_id.upper()
        if "PCI" not in upper_pnp and "USB" not in upper_pnp:
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
        if loc is not None:
            pci, acpi = loc[:2]
            module.pci_path = format_pci_path(pci)
            module.acpi_path = format_acpi_path(acpi)
        else:
            network_info.status.type = StatusType.PARTIAL
            network_info.status.messages.append(
                f"Could not determine location paths for NIC with PNPDeviceID: {pnp_device_id}"
            )

        module.manufacturer = manufacturer
        module.name = name
        network_info.modules.append(module)

    return network_info
