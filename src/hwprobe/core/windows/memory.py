import ctypes

from hwprobe.core.windows.win_enum import ECC_MEMORY_TYPE, MEMORY_TYPE

# todo: refactor to new bindings
from hwprobe.interops.win.legacy.constants import ECC_MULTI_BIT, ECC_SINGLE_BIT
from hwprobe.interops.win.legacy.signatures import GetWmiInfo
from hwprobe.models.memory_models import (
    MemoryInfo,
    MemoryModuleInfo,
    MemoryModuleSlot,
)
from hwprobe.models.size_models import Megabyte
from hwprobe.models.status_models import StatusType


def check_ecc() -> tuple[bool, str]:
    """
    Checks if the system supports ECC memory by querying Win32_PhysicalMemoryArray.

    More specifically, it only returns true if the "MemoryErrorCorrection" property is:
        5 - Single-bit ECC
        6 - Multi-bit ECC

    Returns:
        Tuple[bool, str]: A tuple where the first element indicates if ECC is supported,
                          and the second element is the ECC type as a string.
    """
    query = b"SELECT MemoryErrorCorrection FROM Win32_PhysicalMemoryArray"

    # NOTE[kernel]:
    #   I don't really know how to implement support for multiple memory arrays,
    #   so we'll just check the first one for now.
    buf_size = 256 * 1

    buffer = ctypes.create_string_buffer(buf_size)
    GetWmiInfo(query, b"ROOT\\CIMV2", buffer, buf_size)

    raw_data = buffer.value.decode("utf-8", errors="ignore")

    if not raw_data:
        return False, "Unknown"

    first_line = raw_data.split("\n")[0]
    parsed_data = {x.split("=", 1)[0]: x.split("=", 1)[1] for x in first_line.split("|") if "=" in x}
    ecc_type = parsed_data.get("MemoryErrorCorrection", "Unknown")

    supported = False

    if ecc_type.isdigit():
        ecc_type = int(ecc_type)
        if ecc_type == ECC_SINGLE_BIT or ecc_type == ECC_MULTI_BIT:
            supported = True

    return supported, (ECC_MEMORY_TYPE[ecc_type] if ecc_type in ECC_MEMORY_TYPE else "Unknown")


def fetch_wmi_memory_info() -> MemoryInfo:
    memory_info = MemoryInfo()

    # 256 bytes per property, 9 properties, 6 modules
    buf_size = 256 * 9 * 8
    buffer = ctypes.create_string_buffer(buf_size)

    GetWmiInfo(
        b"SELECT BankLabel, Capacity, Manufacturer, PartNumber, Speed, DeviceLocator, SMBIOSMemoryType, DataWidth, TotalWidth FROM Win32_PhysicalMemory",
        b"ROOT\\CIMV2",
        buffer,
        buf_size,
    )

    """
    `raw_data` is in the following format:
    BankLabel=...|Capacity=...|...
    BankLabel=...|Capacity=...|...
    ...
    
    Each module is separated by a newline; and for each module,
    its properties are separated by a '|' character
    """

    raw_data = buffer.value.decode("utf-8", errors="ignore")

    if not raw_data:
        memory_info.status.type = StatusType.FAILED
        memory_info.status.messages.append("WMI query returned no data")
        return memory_info

    for line in raw_data.split("\n"):
        if not line or "|" not in line:
            continue

        module = MemoryModuleInfo()
        unparsed = line.split("|")

        parsed_data = {x.split("=", 1)[0]: x.split("=", 1)[1] for x in unparsed if "=" in x}

        bank_label = parsed_data["BankLabel"]
        capacity = parsed_data["Capacity"]
        manufacturer = parsed_data["Manufacturer"]
        part_number = parsed_data["PartNumber"]
        speed = parsed_data["Speed"]
        device_locator = parsed_data["DeviceLocator"]
        smbios_mem_type = parsed_data["SMBIOSMemoryType"]
        data_width = parsed_data["DataWidth"]
        total_width = parsed_data["TotalWidth"]

        capacity = int(capacity) if capacity.isdigit() else 0

        module.capacity = Megabyte(capacity=capacity // (1024 * 1024))
        module.manufacturer = manufacturer.strip() if manufacturer else None
        module.part_number = part_number.strip() if part_number else None

        slot = MemoryModuleSlot(
            bank=bank_label.strip() if bank_label else None,
            channel=device_locator.strip() if device_locator else None,
        )
        module.slot = slot

        # The speed is already reported as MHz
        module.frequency_mhz = int(speed) if speed.isdigit() else None

        if smbios_mem_type:
            smbios_mem_type = smbios_mem_type.strip()
            module.type = MEMORY_TYPE.get(int(smbios_mem_type), "Unknown")

        if data_width and total_width:
            if int(total_width) > int(data_width):
                module.supports_ecc = True
            else:
                module.supports_ecc = False

        # NOTE[kernel]:
        #   I don't know if it's same to assume this,
        #   but I believe Win32_PhysicalMemoryArray indicates
        #   towards all memory modules in the system.
        #
        #   Apparently, this isn't supposed to be like this,
        #   but I cannot find a better way to determine ECC support per module.
        ecc_supported, ecc_type = check_ecc()
        module.supports_ecc = ecc_supported
        module.ecc_type = ecc_type

        memory_info.modules.append(module)

    return memory_info


def fetch_memory_info() -> MemoryInfo:
    return fetch_wmi_memory_info()
