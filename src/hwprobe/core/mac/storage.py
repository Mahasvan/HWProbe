
from hwprobe.models.size_models import Megabyte
from hwprobe.models.status_models import StatusType
from hwprobe.models.storage_models import StorageInfo, DiskInfo

STORAGE_MAP = {
    "Solid State": "Solid State Drive (SSD)",
    "Rotational": "Hard Disk Drive (HDD)",
}

"""
This module fetches storage information on macOS using a C++ extension that interfaces with IOKit. 
Refer interops/mac/bindings/storage_info.py for the C++ extension implementation.
"""


def fetch_storage_info() -> StorageInfo:
    storage_info = StorageInfo()

    try:
        from hwprobe.interops.mac.bindings.storage_info import get_storage_info, StorageDeviceProperties
        disk_list: list[StorageDeviceProperties] = get_storage_info()

    except FileNotFoundError as e:
        storage_info.status.type = StatusType.FAILED
        storage_info.status.messages.append(f"libdevice_info.dylib not found – rebuild the CMake project: {e}")
        return storage_info

    except RuntimeError as e:
        storage_info.status.type = StatusType.FAILED
        storage_info.status.messages.append(f"IOKit storage enumeration failed: {e}")
        return storage_info

    except Exception as e:
        storage_info.status.type = StatusType.FAILED
        storage_info.status.messages.append(f"Unexpected error loading storage binding: {e}")
        return storage_info

    for device in disk_list:
        disk = DiskInfo()

        name = device.product_name.strip() if device.product_name else None
        disk.model = name if name else None

        manufacturer = device.vendor_name.strip() if device.vendor_name else None
        if manufacturer:
            disk.manufacturer = manufacturer
        elif name and "apple" in name.lower():
            disk.manufacturer = "Apple"

        medium_type = device.medium_type.strip() if device.medium_type else ""
        interconnect = device.interconnect.strip() if device.interconnect else ""
        location = device.location.strip() if device.location else ""

        disk.connector = interconnect if interconnect else None
        disk.location = location if location else "Unknown"

        if interconnect.lower() == "pci-express":
            disk.type = "Non-Volatile Memory Express (NVMe)"
        elif medium_type:
            disk.type = STORAGE_MAP.get(medium_type, medium_type)
        else:
            disk.type = "Unknown"

        if device.size_bytes:
            disk.size = Megabyte(capacity=device.size_bytes // (1024 * 1024))

        bsd_name = device.bsd_name.strip() if device.bsd_name else None
        disk.identifier = bsd_name if bsd_name else None

        storage_info.modules.append(disk)

    return storage_info
