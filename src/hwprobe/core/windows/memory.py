from typing import Optional

from hwprobe.core.windows.win_enum import ECC_MEMORY_TYPE, MEMORY_TYPE
from hwprobe.interops.win.bindings import wmi
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
    """
    data = wmi.get_wmi_data("Win32_PhysicalMemoryArray", ["MemoryErrorCorrection"])
    if not data:
        return False, "Unknown"

    correction_type = data[0].get("MemoryErrorCorrection", "")
    if not correction_type:
        return False, "Unknown"

    try:
        correction_type = int(correction_type)
    except ValueError:
        return False, "Unknown"

    return correction_type in (5, 6), ECC_MEMORY_TYPE.get(correction_type, "Unknown")


def fetch_wmi_memory_info() -> MemoryInfo:
    memory_info = MemoryInfo()
    records = wmi.get_wmi_data(
        "Win32_PhysicalMemory",
        [
            "BankLabel",
            "Capacity",
            "Manufacturer",
            "PartNumber",
            "Speed",
            "DeviceLocator",
            "SMBIOSMemoryType",
            "DataWidth",
            "TotalWidth",
        ],
    )

    if not records:
        memory_info.status.type = StatusType.FAILED
        memory_info.status.messages.append("WMI query returned no data")
        return memory_info

    for record in records:
        module = MemoryModuleInfo()
        bank_label = record.get("BankLabel").strip()
        capacity = int(record.get("Capacity"))
        manufacturer = record.get("Manufacturer").strip()
        part_number = record.get("PartNumber").strip()
        speed = int(record.get("Speed"))
        device_locator = record.get("DeviceLocator").strip()
        smbios_mem_type = int(record.get("SMBIOSMemoryType"))
        data_width = int(record.get("DataWidth"))
        total_width = int(record.get("TotalWidth"))

        if capacity is not None:
            module.capacity = Megabyte(capacity=capacity // (1024 * 1024))

        module.manufacturer = manufacturer
        module.part_number = part_number
        module.slot = MemoryModuleSlot(bank=bank_label, channel=device_locator)

        # The speed is already reported as MHz.
        module.frequency_mhz = speed

        if smbios_mem_type is not None:
            module.type = MEMORY_TYPE.get(smbios_mem_type, "Unknown")

        if data_width is not None and total_width is not None:
            module.supports_ecc = total_width > data_width

        # WMI output takes precedence over data width comparison for ECC support.
        ecc_supported, ecc_type = check_ecc()
        module.supports_ecc = ecc_supported
        module.ecc_type = ecc_type

        memory_info.modules.append(module)

    return memory_info


def fetch_memory_info() -> MemoryInfo:
    return fetch_wmi_memory_info()
