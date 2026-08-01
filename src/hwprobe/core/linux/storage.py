import os

from hwprobe.models.size_models import Megabyte
from hwprobe.models.status_models import StatusType, Status
from hwprobe.models.storage_models import StorageInfo, DiskInfo


def _fetch_emmc_info(folder: str) -> tuple[DiskInfo, Status]:
    """
    Helper function for eMMC devices, which have different places to get some data.

    Args:
        folder (str) - "sda", "mmcblk0", etc.
    """
    path = f"/sys/block/{folder}"
    disk = DiskInfo()
    status = Status()

    disk.identifier = folder.strip()

    model = open(f"{path}/device/name").read().strip()
    disk.model = model
    if not model:
        status.type = StatusType.PARTIAL
        status.messages.append("Disk Model could not be found")

    removable = open(f"{path}/removable").read().strip()

    if removable == "0":
        disk.type = "Embedded MultiMediaCard (eMMC)"
    else:
        disk.type = "Secure Digital (SD)"

    disk.location = "Internal" if removable == "0" else "External"
    disk.connector = "Unknown"

    vendor_id = open(f"{path}/device/manfid").read().strip()
    disk.vendor_id = vendor_id
    if not vendor_id:
        status.type = StatusType.PARTIAL
        status.messages.append("Disk vendor id could not be found")

    device_id = open(f"{path}/device/oemid").read().strip()
    disk.device_id = device_id
    if not device_id:
        status.type = StatusType.PARTIAL
        status.messages.append("Disk device id could not be found")

    size = open(f"{path}/size").read().strip()
    size_in_bytes = int(size) * 512
    disk.size = Megabyte(capacity=(size_in_bytes // 1024 ** 2))

    return disk, status


def _fetch_standard_disk_info(folder: str) -> tuple[DiskInfo, Status]:
    """
    Helper function for NVMe and SATA (sd*,nvme*) storage devices.

    Args:
        folder (str) - "nvme0n1", "sda", etc.
    """
    path = f"/sys/block/{folder}"
    disk = DiskInfo()
    status = Status()

    disk.identifier = folder.strip()

    model = open(f"{path}/device/model").read().strip()
    if model:
        disk.model = model
    else:
        status.type = StatusType.PARTIAL
        status.messages.append("Disk Model could not be found")

    rotational = open(f"{path}/queue/rotational").read().strip()
    removable = open(f"{path}/removable").read().strip()

    disk.type = (
        "Solid State Drive (SSD)"
        if rotational == "0"
        else "Hard Disk Drive (HDD)"
    )
    disk.location = "Internal" if removable == "0" else "External"

    if "nvme" in folder:
        disk.connector = "PCIe"
        disk.type = "Non-Volatile Memory Express (NVMe)"
        disk.device_id = open(f"{path}/device/device/device").read().strip()
        disk.vendor_id = open(f"{path}/device/device/vendor").read().strip()
    elif "sd" in folder:
        disk.connector = "SCSI"
        disk.vendor_id = open(f"{path}/device/vendor").read().strip()
    else:
        disk.connector = "Unknown"

    size = open(f"{path}/size").read().strip()
    size_in_bytes = int(size) * 512
    disk.size = Megabyte(capacity=(size_in_bytes // 1024 ** 2))

    return disk, status


def fetch_storage_info() -> StorageInfo:
    storage_info = StorageInfo()

    if not os.path.isdir("/sys/block"):
        storage_info.status.type = StatusType.FAILED
        storage_info.status.messages.append("The /sys/block directory does not exist")
        return storage_info

    for folder in os.listdir("/sys/block"):
        try:
            path = f"/sys/block/{folder}"

            # Skip partitions (they have a 'partition' file)
            if os.path.exists(f"{path}/partition"):
                continue

            # Skip eMMC boot and RPMB partitions
            if "boot" in folder or "rpmb" in folder:
                continue

            if folder.startswith("mmc"):
                disk, status = _fetch_emmc_info(folder)
            elif "nvme" in folder or "sd" in folder:
                disk, status = _fetch_standard_disk_info(folder)
            else:
                continue

            storage_info.status.type = status.type
            storage_info.status.messages.extend(status.messages)
            storage_info.modules.append(disk)

        except Exception as e:
            storage_info.status.type = StatusType.PARTIAL
            storage_info.status.messages.append(f"Disk Info ({folder}): {str(e)}")

    return storage_info
