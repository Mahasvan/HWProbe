from hwprobe.core.windows.win_enum import ECC_MEMORY_TYPE, MEMORY_TYPE
from hwprobe.interops.win.bindings.wmi import get_wmi_data
from hwprobe.models.memory_models import (
    MemoryInfo,
    MemoryModuleInfo,
    MemoryModuleSlot,
)
from hwprobe.models.size_models import Megabyte
from hwprobe.models.status_models import StatusType

# Win32_PhysicalMemoryArray.MemoryErrorCorrection values
# https://learn.microsoft.com/en-us/windows/win32/cimwin32prov/win32-physicalmemoryarray
_ECC_SINGLE_BIT = 5
_ECC_MULTI_BIT = 6


def check_ecc() -> tuple[bool, str]:
    """
    Checks if the system supports ECC memory by querying Win32_PhysicalMemoryArray.

    Returns true only if MemoryErrorCorrection is:
        5 - Single-bit ECC
        6 - Multi-bit ECC
    """
    try:
        rows = get_wmi_data("Win32_PhysicalMemoryArray", ["MemoryErrorCorrection"])
    except RuntimeError:
        return False, "Unknown"

    if not rows:
        return False, "Unknown"

    raw = rows[0].get("MemoryErrorCorrection", "")
    if not raw.isdigit():
        return False, "Unknown"

    ecc_type = int(raw)
    supported = ecc_type in (_ECC_SINGLE_BIT, _ECC_MULTI_BIT)
    return supported, ECC_MEMORY_TYPE.get(ecc_type, "Unknown")


def fetch_wmi_memory_info() -> MemoryInfo:
    memory_info = MemoryInfo()

    fields = [
        "BankLabel",
        "Capacity",
        "Manufacturer",
        "PartNumber",
        "Speed",
        "DeviceLocator",
        "SMBIOSMemoryType",
        "DataWidth",
        "TotalWidth",
    ]

    try:
        rows = get_wmi_data("Win32_PhysicalMemory", fields)
    except RuntimeError as e:
        memory_info.status.type = StatusType.FAILED
        memory_info.status.messages.append(str(e))
        return memory_info

    if not rows:
        memory_info.status.type = StatusType.FAILED
        memory_info.status.messages.append("WMI query returned no data")
        return memory_info

    # Query the array once — all modules share the same ECC capability.
    ecc_supported, ecc_type = check_ecc()

    for row in rows:
        module = MemoryModuleInfo()

        capacity = row.get("Capacity", "")
        capacity = int(capacity) if capacity.isdigit() else 0
        module.capacity = Megabyte(capacity=capacity // (1024 * 1024))

        manufacturer = row.get("Manufacturer", "")
        module.manufacturer = manufacturer.strip() if manufacturer else None

        part_number = row.get("PartNumber", "")
        module.part_number = part_number.strip() if part_number else None

        bank_label = row.get("BankLabel", "")
        device_locator = row.get("DeviceLocator", "")
        module.slot = MemoryModuleSlot(
            bank=bank_label.strip() if bank_label else None,
            channel=device_locator.strip() if device_locator else None,
        )

        speed = row.get("Speed", "")
        module.frequency_mhz = int(speed) if speed.isdigit() else None

        smbios_mem_type = row.get("SMBIOSMemoryType", "")
        if smbios_mem_type and smbios_mem_type.isdigit():
            module.type = MEMORY_TYPE.get(int(smbios_mem_type), "Unknown")

        data_width = row.get("DataWidth", "")
        total_width = row.get("TotalWidth", "")
        if data_width.isdigit() and total_width.isdigit():
            module.supports_ecc = int(total_width) > int(data_width)

        # Win32_PhysicalMemoryArray reports ECC for the whole array, not per
        # module. Override the per-module heuristic above with the array value.
        module.supports_ecc = ecc_supported
        module.ecc_type = ecc_type

        memory_info.modules.append(module)

    return memory_info


def fetch_memory_info() -> MemoryInfo:
    return fetch_wmi_memory_info()
