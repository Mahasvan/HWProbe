from ctypes import byref

# todo: refactor to new bindings
from hwprobe.interops.win.legacy.constants import STATUS_OK
from hwprobe.interops.win.legacy.signatures import FetchSMBIOSData
from hwprobe.interops.win.legacy.structs import SMBIOSHwInfo
from hwprobe.models.baseboard_models import BaseboardInfo
from hwprobe.models.status_models import Status, StatusType


def fetch_baseboard_info() -> BaseboardInfo:
    baseboard_info = BaseboardInfo(status=Status(type=StatusType.SUCCESS))
    info = SMBIOSHwInfo()

    result = FetchSMBIOSData(byref(info))

    if result != STATUS_OK:
        baseboard_info.status.type = StatusType.FAILED
        baseboard_info.status.messages.append("Failed to fetch SMBIOS hardware info for Baseboard")
        return baseboard_info

    manufacturer = info.motherboardManufacturer.decode(errors="ignore").rstrip("\x00")
    model = info.motherboardModel.decode(errors="ignore").rstrip("\x00")
    chassis_type = info.chassisType.decode(errors="ignore").rstrip("\x00")
    cpu_socket = info.cpuSocket.decode(errors="ignore").rstrip("\x00")

    baseboard_info.manufacturer = manufacturer if manufacturer else None
    baseboard_info.model = model if model else None
    baseboard_info.chassis_type = chassis_type if chassis_type else None
    baseboard_info.cpu_socket = cpu_socket if cpu_socket else None

    return baseboard_info
