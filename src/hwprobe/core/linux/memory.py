import os
from abc import ABC, abstractmethod
from typing import Optional, List

from hwprobe.core.linux.dmi_decode import MEMORY_TYPE, get_string_entry
from hwprobe.models.memory_models import MemoryInfo, MemoryModuleInfo, MemoryModuleSlot
from hwprobe.models.size_models import Kilobyte, Megabyte, StorageSize
from hwprobe.models.status_models import StatusType

# Thank you to [Quist](https://github.com/nadiaholmquist) for helping with our understanding of this.


class DMIProvider(ABC):
    """
    Interface for providing DMI data to the library.
    """
    
    @abstractmethod
    def get_entries_by_type(self, t: int) -> List[bytes]:
        """
        Return raw DMI Type <t> entries.
        
        Each entry is the complete binary structure from:
        - /sys/firmware/dmi/entries/<t>-*/raw (requires read access)
        - dmidecode -t <t> --dump-bin output
        - Pre-saved binary files
        - Mock/test data
        
        Returns:
            List of raw DMI Type <t> entries (one bytes object per memory slot)
            
        Raises: ?
        """
        raise NotImplementedError("DMIProvider.get_entries_by_type not implemented")


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


def _parse_single_entry(value: bytes) -> Optional[MemoryModuleInfo]:
    """
    Parse a single DMI Type 17 entry into MemoryModuleInfo.
    
    Args:
        value: Raw binary DMI Type 17 structure
        
    Returns:
        MemoryModuleInfo if entry is valid and populated, None otherwise
    """
    try:
        if len(value) < 0x20 or value[0x0] != 17:
            return None
        
        length_field = value[0x1]
        strings = value[length_field : len(value)].split(b"\0")

        module = MemoryModuleInfo()
        
        module.part_number = _part_no(strings, value)

        if (t := _dimm_type(value)) is not None:
            module.type = t
        
        if (slot := _dimm_slot(strings, value)) is not None:
            module.slot = slot

        module.manufacturer = get_string_entry(strings, value[0x17])
        
        if (capacity := _dimm_capacity(value)) is not None:
            module.capacity = capacity
        
        module.supports_ecc = _ecc_support(value)
        module.frequency_mhz = _dimm_speed(value)

        return module
        
    except Exception:
        return None


def fetch_memory_info(provider: Optional[DMIProvider] = None) -> MemoryInfo:
    """
    Fetch memory information using user-provided DMI data.
    
    The library never reads /sys/firmware/dmi itself. Users must implement
    DMIProvider to supply raw DMI Type <type> data, giving them full control
    over data acquisition and permissions.
    
    Args:
        provider: DMIProvider implementation (REQUIRED)
        
    Returns:
        MemoryInfo with parsed memory modules and status
        
    Example:
        >>> class SysfsProvider(DMIProvider):
        ...     def get_entries_by_type(self, t: int) -> List[bytes]:
        ...         # Read from /sys/firmware/dmi/entries/<t>-*/raw
        ...         pass
        >>> provider = SysfsProvider()
        >>> hm = HardwareManager(provider)
        
    References:
        SMBIOS Specification - Section 7.18 - Memory Device (Type 17)
        https://www.dmtf.org/sites/default/files/standards/documents/DSP0134_3.9.0.pdf
    """
    memory_info = MemoryInfo()

    if provider is None:
        memory_info.status.type = StatusType.FAILED
        memory_info.status.messages.append("No DMIProvider provided")
        return memory_info

    try:
        raw_entries = provider.get_entries_by_type(17)
    except Exception as e:
        memory_info.status.type = StatusType.FAILED
        memory_info.status.messages.append(f"Failed to retrieve DMI Type 17 entries")
        memory_info.status.messages.append(str(e))
        return memory_info
    
    if not raw_entries:
        memory_info.status.type = StatusType.FAILED
        memory_info.status.messages.append("No DMI Type 17 entries provided by DMIProvider.")
        return memory_info

    for raw_entry in raw_entries:
        module = _parse_single_entry(raw_entry)

        # SMBIOS/DMI describe the physical slot, not the actual populated module. 
        # If the "module" has a capacity of 0, it means the slot is empty.
        if module:
            # Better to do it here to not signify a PARTIAL if one of the entries is empty (capacity 0)
            if module.capacity is None or module.capacity.capacity > 0:
                memory_info.modules.append(module)
        else:
            memory_info.status.type = StatusType.PARTIAL
            memory_info.status.messages.append("Failed to parse one or more DMI entries")

    return memory_info
