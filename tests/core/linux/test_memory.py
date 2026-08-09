from typing import List, Optional

from hwprobe.core.linux.memory import (
    DMIProvider,
    _dimm_capacity,
    _dimm_slot,
    _dimm_speed,
    _dimm_type,
    _ecc_support,
    _part_no,
    fetch_memory_info,
)
from hwprobe.models.memory_models import MemoryModuleSlot
from hwprobe.models.size_models import Kilobyte, Megabyte
from hwprobe.models.status_models import StatusType


class _FakeDMIProvider(DMIProvider):
    """Test double that returns pre-built raw DMI Type 17 entries."""

    def __init__(self, entries: Optional[List[bytes]] = None, error: Optional[Exception] = None):
        self._entries = entries or []
        self._error = error

    def get_entries_by_type(self, t: int) -> List[bytes]:
        if self._error is not None:
            raise self._error
        return self._entries


class TestPartNo:
    """Tests for the _part_no helper function."""

    def test_part_no_with_dimm_in_value(self):
        """Part number should be returned when 'dimm' is in the value."""
        # Create a value with "DIMM" and proper structure
        value = bytearray(0x1B)
        value[0x1A] = 1  # String index 1
        strings = [b"PART-1234"]
        # Need "dimm" somewhere in the value for the check
        value[0:4] = b"DIMM"

        result = _part_no(strings, bytes(value))
        assert result == "PART-1234"

    def test_part_no_without_dimm_in_value(self):
        """Part number should be None when 'dimm' is not in the value."""
        value = bytearray(0x1B)
        value[0x1A] = 1
        strings = [b"PART-1234"]
        # No "dimm" in value
        value[0:4] = b"TEST"

        result = _part_no(strings, bytes(value))
        assert result is None

    def test_part_no_dimm_case_insensitive(self):
        """The 'dimm' check should be case insensitive."""
        value = bytearray(0x1B)
        value[0x1A] = 1
        strings = [b"PART-5678"]
        value[0:4] = b"dimm"  # lowercase

        result = _part_no(strings, bytes(value))
        assert result == "PART-5678"


class TestDimmType:
    """Tests for the _dimm_type helper function."""

    def test_dimm_type_ddr4(self):
        value = bytearray(0x13)
        value[0x12] = 0x1A  # DDR4

        result = _dimm_type(bytes(value))
        assert result == "DDR4"

    def test_dimm_type_ddr3(self):
        value = bytearray(0x13)
        value[0x12] = 0x18  # DDR3

        result = _dimm_type(bytes(value))
        assert result == "DDR3"

    def test_dimm_type_unknown(self):
        value = bytearray(0x13)
        value[0x12] = 0xFF  # Not in MEMORY_TYPE

        result = _dimm_type(bytes(value))
        assert result is None


class TestDimmSlot:
    """Tests for the _dimm_slot helper function."""

    def test_dimm_slot_valid(self):
        value = bytearray(0x12)
        value[0x10] = 1  # Channel string index
        value[0x11] = 2  # Bank string index
        strings = [b"Channel A", b"Bank 0"]

        result = _dimm_slot(strings, bytes(value))
        assert result is not None
        assert isinstance(result, MemoryModuleSlot)
        assert result.channel == "Channel A"
        assert result.bank == "Bank 0"

    def test_dimm_slot_zero_index_returns_unknown(self):
        value = bytearray(0x12)
        value[0x10] = 0  # Zero index means "Unknown"
        value[0x11] = 0
        strings = []

        result = _dimm_slot(strings, bytes(value))
        assert result is not None
        assert result.channel == "Unknown"
        assert result.bank == "Unknown"


class TestDimmCapacity:
    """Tests for the _dimm_capacity helper function."""

    def test_dimm_capacity_megabytes(self):
        value = bytearray(0x20)
        size_mb = 8192  # 8 GB
        value[0x0C:0x0E] = size_mb.to_bytes(2, "little")

        result = _dimm_capacity(bytes(value))
        assert result is not None
        assert isinstance(result, Megabyte)
        assert result.capacity == 8192

    def test_dimm_capacity_kilobytes(self):
        value = bytearray(0x20)
        # Bit 15 set means kilobytes
        size_kb = 2048 | 0x8000
        value[0x0C:0x0E] = size_kb.to_bytes(2, "little")

        result = _dimm_capacity(bytes(value))
        assert result is not None
        assert isinstance(result, Kilobyte)
        assert result.capacity == size_kb

    def test_dimm_capacity_extended_size(self):
        value = bytearray(0x20)
        value[0x0C:0x0E] = (0x7FFF).to_bytes(2, "little")  # Use extended size
        value[0x1C:0x20] = (32768).to_bytes(4, "little")  # 32 GB

        result = _dimm_capacity(bytes(value))
        assert result is not None
        assert isinstance(result, Megabyte)
        assert result.capacity == 32768

    def test_dimm_capacity_unknown(self):
        value = bytearray(0x20)
        value[0x0C:0x0E] = (0xFFFF).to_bytes(2, "little")  # Unknown size

        result = _dimm_capacity(bytes(value))
        assert result is None


class TestEccSupport:
    """Tests for the _ecc_support helper function."""

    def test_ecc_support_true(self):
        value = bytearray(0x0C)
        value[0x08:0x0A] = (72).to_bytes(2, "little")  # Total width
        value[0x0A:0x0C] = (64).to_bytes(2, "little")  # Data width

        result = _ecc_support(bytes(value))
        assert result is True

    def test_ecc_support_false(self):
        value = bytearray(0x0C)
        value[0x08:0x0A] = (64).to_bytes(2, "little")  # Total width
        value[0x0A:0x0C] = (64).to_bytes(2, "little")  # Data width

        result = _ecc_support(bytes(value))
        assert result is False


class TestDimmSpeed:
    """Tests for the _dimm_speed helper function."""

    def test_dimm_speed_normal(self):
        value = bytearray(0x58)
        value[0x15:0x17] = (3200).to_bytes(2, "little")

        result = _dimm_speed(bytes(value))
        assert result == 3200

    def test_dimm_speed_extended(self):
        value = bytearray(0x58)
        value[0x15:0x17] = (0xFFFF).to_bytes(2, "little")  # Use extended speed
        value[0x54:0x58] = (4800).to_bytes(4, "little")

        result = _dimm_speed(bytes(value))
        assert result == 4800

    def test_dimm_speed_unknown(self):
        value = bytearray(0x58)
        value[0x15:0x17] = (0).to_bytes(2, "little")  # Unknown speed

        result = _dimm_speed(bytes(value))
        assert result is None


class TestLinuxMemory:
    def test_fetch_memory_info_no_provider(self):
        memory_info = fetch_memory_info(provider=None)

        assert memory_info.status.type == StatusType.FAILED
        assert any("No DMIProvider provided" in msg for msg in memory_info.status.messages)

    def test_fetch_memory_info_provider_raises(self):
        provider = _FakeDMIProvider(error=PermissionError("Permission denied"))

        memory_info = fetch_memory_info(provider=provider)

        assert memory_info.status.type == StatusType.FAILED
        assert any("Failed to retrieve DMI Type 17 entries" in msg for msg in memory_info.status.messages)
        assert any("Permission denied" in msg for msg in memory_info.status.messages)

    def test_fetch_memory_info_no_entries(self):
        provider = _FakeDMIProvider(entries=[])

        memory_info = fetch_memory_info(provider=provider)

        assert memory_info.status.type == StatusType.FAILED
        assert any("No DMI Type 17 entries provided by DMIProvider" in msg for msg in memory_info.status.messages)

    def _create_dmi_blob(
        self,
        size_mb=8192,
        total_width=72,
        data_width=64,
        speed=3200,
        mem_type=0x1A,  # DDR4
        part_no="1234-5678",
        dev_loc="DIMM 0",
        bank_loc="BANK 0",
        manufacturer="Acme Corp",
        extended_size=None,
        extended_speed=None,
    ):

        # Header length
        length = 0x5C

        data = bytearray(length)
        data[0x00] = 17  # SMBIOS Type 17 (Memory Device)
        data[0x01] = length

        # Strings - include "DIMM" in the data for _part_no check
        strings_bytes = b""
        string_indices = {}
        current_index = 1

        for s in [dev_loc, bank_loc, manufacturer, part_no]:
            if s:
                strings_bytes += s.encode("ascii") + b"\0"
                string_indices[s] = current_index
                current_index += 1

        # Set indices
        data[0x10] = string_indices.get(dev_loc, 0)
        data[0x11] = string_indices.get(bank_loc, 0)
        data[0x17] = string_indices.get(manufacturer, 0)
        data[0x1A] = string_indices.get(part_no, 0)

        # Set Type
        data[0x12] = mem_type

        # Set Widths
        data[0x08:0x0A] = total_width.to_bytes(2, "little")
        data[0x0A:0x0C] = data_width.to_bytes(2, "little")

        # Set Size
        if extended_size is not None:
            data[0x0C:0x0E] = (0x7FFF).to_bytes(2, "little")
            data[0x1C:0x20] = extended_size.to_bytes(4, "little")
        else:
            # Normal size - Bit 15 = 0 for MB.
            data[0x0C:0x0E] = size_mb.to_bytes(2, "little")

        # Set Speed
        if extended_speed is not None:
            data[0x15:0x17] = (0xFFFF).to_bytes(2, "little")
            data[0x54:0x58] = extended_speed.to_bytes(4, "little")
        else:
            data[0x15:0x17] = speed.to_bytes(2, "little")

        # Double null terminator at end of strings
        strings_bytes += b"\0"

        return bytes(data) + strings_bytes

    def test_fetch_memory_info_success(self):
        blob = self._create_dmi_blob()
        provider = _FakeDMIProvider(entries=[blob])

        memory_info = fetch_memory_info(provider=provider)

        assert memory_info.status.type == StatusType.SUCCESS
        assert len(memory_info.modules) == 1
        module = memory_info.modules[0]

        assert module.part_number == "1234-5678"
        assert module.type == "DDR4"
        assert module.slot is not None
        assert module.slot.channel == "DIMM 0"
        assert module.slot.bank == "BANK 0"
        assert module.manufacturer == "Acme Corp"
        assert module.capacity is not None
        assert module.capacity.capacity == 8192
        assert isinstance(module.capacity, Megabyte)
        assert module.supports_ecc == True  # 72 - 64 = 8 = 64/8
        assert module.frequency_mhz == 3200

    def test_fetch_memory_info_non_ecc(self):
        blob = self._create_dmi_blob(total_width=64, data_width=64)
        provider = _FakeDMIProvider(entries=[blob])

        memory_info = fetch_memory_info(provider=provider)
        assert memory_info.modules[0].supports_ecc == False

    def test_fetch_memory_info_unknown_size(self):
        # Size 0xFFFF means unknown
        blob = self._create_dmi_blob()
        # Manually overwrite size to 0xFFFF
        data = bytearray(blob)
        data[0x0C:0x0E] = (0xFFFF).to_bytes(2, "little")
        provider = _FakeDMIProvider(entries=[bytes(data)])

        memory_info = fetch_memory_info(provider=provider)
        # Module is still added, but with unknown (None) capacity
        assert len(memory_info.modules) == 1
        assert memory_info.modules[0].capacity is None
        assert memory_info.status.type == StatusType.SUCCESS

    def test_fetch_memory_info_extended_speed(self):
        blob = self._create_dmi_blob(extended_speed=4800)
        provider = _FakeDMIProvider(entries=[blob])

        memory_info = fetch_memory_info(provider=provider)
        assert memory_info.modules[0].frequency_mhz == 4800

    def test_fetch_memory_info_parsing_error(self):
        # Too short / missing SMBIOS Type 17 header, fails to parse entirely
        provider = _FakeDMIProvider(entries=[b"DIMM"])

        memory_info = fetch_memory_info(provider=provider)
        assert memory_info.status.type == StatusType.PARTIAL
        assert any("Failed to parse one or more DMI entries" in msg for msg in memory_info.status.messages)
        assert len(memory_info.modules) == 0

    def test_fetch_memory_info_kilobyte_capacity(self):
        # 2048 KB. Bit 15 set means 0x8000. 2048 is 0x0800. Total 0x8800.
        size_kb_val = 2048 | 0x8000

        blob = self._create_dmi_blob()
        data = bytearray(blob)
        data[0x0C:0x0E] = size_kb_val.to_bytes(2, "little")
        provider = _FakeDMIProvider(entries=[bytes(data)])

        memory_info = fetch_memory_info(provider=provider)
        module = memory_info.modules[0]
        assert isinstance(module.capacity, Kilobyte)
        # The capacity value stored is the raw value passed to constructor
        assert module.capacity.capacity == size_kb_val

    def test_fetch_memory_info_type_error(self):
        blob = self._create_dmi_blob()
        data = bytearray(blob)
        # Set invalid type (0xFF is not in MEMORY_TYPE)
        data[0x12] = 0xFF
        provider = _FakeDMIProvider(entries=[bytes(data)])

        memory_info = fetch_memory_info(provider=provider)
        # An unmapped memory type isn't fatal; the module is still added with type=None
        assert memory_info.status.type == StatusType.SUCCESS
        assert len(memory_info.modules) == 1
        assert memory_info.modules[0].type is None

    def test_fetch_memory_info_location_error(self):
        blob = self._create_dmi_blob()
        data = bytearray(blob)
        # Set invalid string index for location (0x10) - this will cause IndexError in get_string_entry
        data[0x10] = 0xFF
        provider = _FakeDMIProvider(entries=[bytes(data)])

        memory_info = fetch_memory_info(provider=provider)
        # The invalid index causes an exception in get_string_entry, caught by the outer except
        assert memory_info.status.type == StatusType.PARTIAL
        assert len(memory_info.status.messages) > 0
        assert len(memory_info.modules) == 0

    def test_fetch_memory_info_manufacturer_error(self):
        blob = self._create_dmi_blob()
        data = bytearray(blob)
        # Set invalid string index for manufacturer (0x17) - causes IndexError
        data[0x17] = 0xFF
        provider = _FakeDMIProvider(entries=[bytes(data)])

        memory_info = fetch_memory_info(provider=provider)
        # Invalid index causes exception caught by outer except block
        assert memory_info.status.type == StatusType.PARTIAL
        assert len(memory_info.status.messages) > 0
        assert len(memory_info.modules) == 0

    def test_fetch_memory_info_capacity_error(self, monkeypatch):
        blob = self._create_dmi_blob()
        provider = _FakeDMIProvider(entries=[blob])

        # Mock Megabyte to raise exception to trigger the except block
        def mock_megabyte(**kwargs):
            raise ValueError("Capacity Error")

        monkeypatch.setattr("hwprobe.core.linux.memory.Megabyte", mock_megabyte)

        memory_info = fetch_memory_info(provider=provider)
        # The exception is caught by the per-entry except block in _parse_single_entry
        assert memory_info.status.type == StatusType.PARTIAL
        assert any("Failed to parse one or more DMI entries" in msg for msg in memory_info.status.messages)
        assert len(memory_info.modules) == 0

