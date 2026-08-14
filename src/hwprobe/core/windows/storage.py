from hwprobe.core.windows.win_enum import BUS_TYPE, MEDIA_TYPE
from hwprobe.interops.win.bindings.wmi import get_wmi_data
from hwprobe.models.size_models import Megabyte
from hwprobe.models.status_models import StatusType
from hwprobe.models.storage_models import DiskInfo, StorageInfo


def fetch_wmi_storage_info() -> StorageInfo:
    """
    Fetch storage information via WMI (MSFT_PhysicalDisk from the Storage
    namespace). Returns a StorageInfo object with all detected disks.
    """
    storage_info = StorageInfo()

    fields = ["FriendlyName", "MediaType", "BusType", "Size", "Manufacturer", "Model"]

    try:
        rows = get_wmi_data(
            "MSFT_PhysicalDisk",
            fields,
            namespace=r"ROOT\Microsoft\Windows\Storage",
        )
    except RuntimeError as e:
        storage_info.status.type = StatusType.FAILED
        storage_info.status.messages.append(str(e))
        return storage_info

    for row in rows:
        disk = DiskInfo()

        friendly_name = row.get("FriendlyName", "")
        media_type = row.get("MediaType", "")
        bus_type = row.get("BusType", "")
        size = row.get("Size", "")
        manufacturer = row.get("Manufacturer", "")
        model = row.get("Model", "")

        disk.model = model.strip() if model else friendly_name.strip() if friendly_name else None
        disk.manufacturer = manufacturer.strip() if manufacturer else None
        disk.type = MEDIA_TYPE.get(int(media_type), "Unknown") if media_type and media_type.isdigit() else "Unknown"
        disk.size = Megabyte(capacity=int(size) // (1024 * 1024)) if size and size.isdigit() else None

        conn_type, location = None, None
        if bus_type and bus_type.isdigit():
            bt = BUS_TYPE.get(int(bus_type))
            if bt:
                conn_type = bt["type"]
                location = bt["location"]

        disk.connector = conn_type
        disk.location = location

        if conn_type and "nvme" in conn_type.lower():
            disk.type = MEDIA_TYPE.get(4)  # SSD

        storage_info.modules.append(disk)

    if storage_info.modules:
        storage_info.status.type = StatusType.SUCCESS
    else:
        storage_info.status.type = StatusType.FAILED
        storage_info.status.messages.append("No storage modules found")

    return storage_info


def fetch_storage_info() -> StorageInfo:
    return fetch_wmi_storage_info()
