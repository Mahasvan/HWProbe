import os
from typing import Optional

from hwprobe.core.linux.dmi_decode import MEMORY_TYPE, get_string_entry
from hwprobe.models.memory_models import MemoryInfo, MemoryModuleInfo, MemoryModuleSlot
from hwprobe.models.size_models import Kilobyte, Megabyte, StorageSize
from hwprobe.models.status_models import StatusType

# Thank you to [Quist](https://github.com/nadiaholmquist) for helping with our understanding of this.


def _part_no(strings: list[bytes], value: bytes) -> Optional[str]:
    """
    Obtains the value at offset 1Ah, which indicates at which index, pre-sanitization,
    in the `strings` list the real string value is stored.

    Which is: `strings[value[0x1A] - 1]`, after obtaining it, it decodes it to `ascii`.
    """
    if not "dimm" in value.upper().decode("latin-1").strip().lower():
        return None

    part_no = get_string_entry(strings, value[0x1A]).strip()
    return part_no


def _dimm_type(value: bytes) -> Optional[str]:
    # DIMM type value is stored at offset 12h
    return MEMORY_TYPE.get(value[0x12])


def _dimm_slot(strings: list[bytes], value: bytes) -> Optional[MemoryModuleSlot]:
    return MemoryModuleSlot(channel=get_string_entry(strings, value[0x10]), bank=get_string_entry(strings, value[0x11]))


def _dimm_capacity(value: bytes) -> Optional[StorageSize]:
    """
    Looks at the 2 bytes at offset 0Ch to determine its size;
    in case the value of these 2 bytes is equal to 0x7FFF, it looks at the 4 bytes
    at the Extended Size, which is at offset 1Ch.

    In case the value at offset 0Ch is equal to 0xFFFF,
    it would mean that the size is unknown.

    If the 15th bit value is `0`, the size is represented in MB. Otherwise, it is in KB.
    Note: Extended size (at 0x1C) is always in megabytes per SMBIOS spec.
    """
    size = int.from_bytes(value[0x0C:0x0E], "little")
    if size == 0xFFFF:
        # Unknown size
        return None

    if size == 0x7FFF:
        # Extended size: 4 bytes at offset 1Ch, always in MB per SMBIOS spec
        size = int.from_bytes(value[0x1C:0x20], "little")
        return Megabyte(capacity=size)

    if (size >> 15) & 1 == 0:
        # Size is in Megabytes
        return Megabyte(capacity=size)
    else:
        # Size is in Kilobytes
        return Kilobyte(capacity=size)


def _ecc_support(value: bytes) -> Optional[bool]:
    """
    In a memory module with Data Width 64 bits, there are 8 more bits with an error correcting code.
    so, the Total Width would be 64+8 = 72 bits.

    We can check if the TotalWidth is greater than DataWidth. If true, it has ECC support
    """
    total_width = int.from_bytes(value[0x08:0x0A], "little")
    data_width = int.from_bytes(value[0x0A:0x0C], "little")

    if total_width > data_width:
        return True
    return False


def _dimm_speed(value: bytes) -> Optional[int]:
    """
    The speed of the RAM module (in MT/s) is stored in the offset 0x15 to 0x17.
    if the value of these 4 bytes is 0x0000, then the speed is unknown.
    If the value is 0xFFFF, then the speed is in the Extended Speed field,
    which is in the offset 0x54 to 0x58
    """
    ram_speed = int.from_bytes(value[0x15:0x17], "little")
    if ram_speed == 0xFFFF:
        ram_speed = int.from_bytes(value[0x54:0x58], "little")

    if ram_speed != 0x0000:
        return ram_speed
    return None


def fetch_memory_info() -> MemoryInfo:
    memory_info = MemoryInfo()

    if not os.path.isdir("/sys/firmware/dmi/entries"):
        memory_info.status.type = StatusType.FAILED
        memory_info.status.messages.append("The /sys/firmware/dmi/entries directory doesn't exist")
        return memory_info

    """
    DMI Documentation: 
    SMBIOS Specification - Section 7.18 - Memory Device (Type 17)
    - https://www.dmtf.org/sites/default/files/standards/documents/DSP0134_3.9.0.pdf
    Other noteworthy mentions:
    - https://android.googlesource.com/kernel/common/+/android-trusty-3.10/Documentation/ABI/testing/sysfs-firmware-dmi
    - https://linux.die.net/man/8/dmidecode
    """

    # Memory Module entries in DMI are of type 17, this is what we want to iterate over
    dmi_entries = os.scandir("/sys/firmware/dmi/entries")
    memory_dmi_types = "17-"
    parent_dirs = [p for p in dmi_entries if p.path.split("/")[-1].startswith(memory_dmi_types)]

    for parent_dir in parent_dirs:
        module = MemoryModuleInfo()
        try:
            with open(f"{parent_dir.path}/raw", "rb") as f:
                value = f.read()
        except PermissionError:
            memory_info.status.type = StatusType.FAILED
            memory_info.status.messages.append("Unable to open /sys/firmware/dmi/entries. Are you root?")
            return memory_info

        except Exception as e:
            memory_info.status.type = StatusType.PARTIAL
            memory_info.status.messages.append("Error Reading DMI Entries: " + str(e))
            continue

        try:
            length_field = value[0x1]
            strings = value[length_field : len(value)].split(b"\0")

            module.part_number = _part_no(strings, value)

            if (t := _dimm_type(value)) is not None:
                module.type = t
            else:
                memory_info.status.type = StatusType.PARTIAL
                memory_info.status.messages.append("Could not get DIMM Type")

            if (slot := _dimm_slot(strings, value)) is not None:
                module.slot = slot
            else:
                memory_info.status.type = StatusType.PARTIAL
                memory_info.status.messages.append("Could not get DIMM Location")

            module.manufacturer = get_string_entry(strings, value[0x17])
            if not module.manufacturer:
                memory_info.status.type = StatusType.PARTIAL
                memory_info.status.messages.append("Could not get DIMM Manufacturer")

            if (capacity := _dimm_capacity(value)) is not None:
                module.capacity = capacity
            else:
                memory_info.status.type = StatusType.PARTIAL
                memory_info.status.messages.append("Could not get DIMM Capacity")

            module.supports_ecc = _ecc_support(value)
            module.frequency_mhz = _dimm_speed(value)

            memory_info.modules.append(module)

        except Exception as e:
            memory_info.status.type = StatusType.PARTIAL
            memory_info.status.messages.append("Error while fetching Memory Info: " + str(e))
    return memory_info
