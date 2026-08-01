import ctypes

from hwprobe.core.windows.win_enum import MEDIA_TYPE, BUS_TYPE
# todo: refactor to new bindings
from hwprobe.interops.win.legacy.signatures import GetWmiInfo
from hwprobe.models.size_models import Megabyte
from hwprobe.models.status_models import StatusType
from hwprobe.models.storage_models import StorageInfo, DiskInfo


def fetch_wmi_storage_info() -> StorageInfo:
    """
    Fetch storage information via WMI using the GetWmiInfo interop.
    Returns a StorageInfo object with all detected disks.
    """
    storage_info = StorageInfo()

    # 256 bytes per property, 6 properties, 10 modules (mostly for NAS systems)
    buf_size = 256 * 6 * 10
    buffer = ctypes.create_string_buffer(buf_size)

    query = (
        b"SELECT FriendlyName, MediaType, BusType, Size, Manufacturer, Model FROM "
        b"MSFT_PhysicalDisk"
    )

    GetWmiInfo(query, b"ROOT\\Microsoft\\Windows\\Storage", buffer, buf_size)

    raw_data = buffer.value.decode("utf-8", errors="ignore")
    if not raw_data:
        storage_info.status.type = StatusType.FAILED
        storage_info.status.messages.append("WMI query returned no data")
        return storage_info

    for line in raw_data.split("\n"):
        if not line or "|" not in line:
            continue

        disk = DiskInfo()
        props = {
            x.split("=", 1)[0]: x.split("=", 1)[1] for x in line.split("|") if "=" in x
        }

        friendly_name = props.get("FriendlyName")
        media_type = props.get("MediaType")
        bus_type = props.get("BusType")
        size = props.get("Size")
        manufacturer = props.get("Manufacturer")
        model = props.get("Model")

        disk.model = (
            model.strip() if model else friendly_name.strip() if friendly_name else None
        )
        disk.manufacturer = manufacturer.strip() if manufacturer else None
        disk.type = (
            MEDIA_TYPE.get(int(media_type), "Unknown")
            if media_type and media_type.isdigit()
            else "Unknown"
        )
        disk.size = (
            Megabyte(capacity=int(size) // (1024 * 1024))
            if size and size.isdigit()
            else None
        )

        # Map bus type
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

    # If at least one module was parsed, mark as success
    if storage_info.modules:
        storage_info.status.type = StatusType.SUCCESS
    else:
        storage_info.status.type = StatusType.FAILED
        storage_info.status.messages.append("No storage modules found")

    return storage_info


def fetch_storage_info() -> StorageInfo:
    return fetch_wmi_storage_info()
