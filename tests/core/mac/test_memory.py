import plistlib
from unittest.mock import patch

import pytest

from hwprobe.core.mac.memory import (
    fetch_memory_info,
    get_arm_ram_info,
    get_ram_size_from_reg,
    get_ram_size_from_system_profiler,
)
from hwprobe.models.memory_models import MemoryInfo
from hwprobe.models.status_models import StatusType

# ── get_ram_size_from_reg ────────────────────────────────────────────────────


class TestGetRamSizeFromReg:
    def test_two_sticks_of_4gb(self):
        """
        "02 00 00 00 00 00 00 00 02 00 00 00 00 00 00 00"
        Non-zero bytes: 0x02, 0x02 => 2 * 4096 = 8192 MB each.
        """
        reg = bytes([0x02, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x02, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
        sizes = get_ram_size_from_reg(reg)
        assert len(sizes) == 2
        assert all(s.capacity == 8192 for s in sizes)
        assert all(s.unit == "MB" for s in sizes)

    def test_empty_reg(self):
        """All zero bytes should produce empty list."""
        reg = b"\x00" * 16
        sizes = get_ram_size_from_reg(reg)
        assert sizes == []

    def test_single_nonzero_byte(self):
        reg = bytes([0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
        sizes = get_ram_size_from_reg(reg)
        assert len(sizes) == 1
        assert sizes[0].capacity == 4096

    def test_return_type_is_megabyte(self):
        from hwprobe.models.size_models import Megabyte

        reg = bytes([0x01])
        sizes = get_ram_size_from_reg(reg)
        assert isinstance(sizes[0], Megabyte)


# ── get_arm_ram_info ─────────────────────────────────────────────────────────


class TestGetArmRamInfo:
    @patch("hwprobe.core.mac.memory.subprocess.check_output")
    def test_single_arm_module(self, mock_co):
        plist_data = [
            {
                "_items": [
                    {
                        "SPMemoryDataType": "8 GB",
                        "dimm_manufacturer": "Samsung",
                        "dimm_type": "LPDDR5",
                    }
                ]
            }
        ]
        mock_co.return_value = plistlib.dumps(plist_data, fmt=plistlib.FMT_XML)

        info = get_arm_ram_info()
        assert len(info.modules) == 1
        assert info.modules[0].manufacturer == "Samsung"
        assert info.modules[0].type == "LPDDR5"
        assert info.modules[0].capacity.capacity == 8
        assert info.modules[0].capacity.unit == "GB"

    @patch("hwprobe.core.mac.memory.subprocess.check_output")
    def test_system_profiler_failure_returns_failed(self, mock_co):
        mock_co.side_effect = FileNotFoundError("system_profiler not found")
        info = get_arm_ram_info()
        assert info.status.type == StatusType.FAILED

    @patch("hwprobe.core.mac.memory.subprocess.check_output")
    def test_arm_ram_status_message_about_partial_data(self, mock_co):
        plist_data = [{"_items": []}]
        mock_co.return_value = plistlib.dumps(plist_data, fmt=plistlib.FMT_XML)

        info = get_arm_ram_info()
        assert any("ARM" in m or "partial" in m.lower() for m in info.status.messages)


# ── get_ram_size_from_system_profiler ────────────────────────────────────────


class TestGetRamSizeFromSystemProfiler:
    @patch("hwprobe.core.mac.memory.subprocess.check_output")
    def test_two_dimms(self, mock_co):
        plist_data = [
            {
                "_items": [
                    {
                        "_items": [
                            {"dimm_size": "8 GB"},
                            {"dimm_size": "8 GB"},
                        ]
                    }
                ]
            }
        ]
        mock_co.return_value = plistlib.dumps(plist_data, fmt=plistlib.FMT_XML)

        sizes = get_ram_size_from_system_profiler()
        assert len(sizes) == 2
        assert all(s.capacity == 8 for s in sizes)
        assert all(s.unit == "GB" for s in sizes)

    @patch("hwprobe.core.mac.memory.subprocess.check_output")
    def test_failure_re_raises(self, mock_co):
        """BUG 3: get_ram_size_from_system_profiler re-raises exceptions."""
        mock_co.side_effect = FileNotFoundError("not found")
        with pytest.raises(FileNotFoundError):
            get_ram_size_from_system_profiler()


# ── fetch_memory_info (x86 path) ────────────────────────────────────────────


class TestFetchMemoryInfoX86:
    def _make_ioreg_plist(self, memory_entry):
        """Build a fake ioreg plist structure with the given memory dict."""
        return plistlib.dumps(
            {
                "IORegistryEntryChildren": [
                    {
                        "IORegistryEntryChildren": [
                            {
                                "IORegistryEntryName": "memory",
                                **memory_entry,
                            }
                        ]
                    }
                ]
            },
            fmt=plistlib.FMT_XML,
        )

    @patch("hwprobe.core.mac.memory.get_ram_size_from_system_profiler")
    @patch("hwprobe.core.mac.memory.subprocess.check_output")
    def test_intel_two_dimms(self, mock_co, mock_sp):
        from hwprobe.models.size_models import Gigabyte

        mock_sp.return_value = [Gigabyte(capacity=8), Gigabyte(capacity=8)]

        memory_entry = {
            "reg": bytes(
                [0x02, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x02, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]
            ),
            "dimm-manufacturer": b"Samsung\x00Samsung\x00",
            "dimm-part-number": b"M471A1K43CB1-CTD\x00M471A1K43CB1-CTD\x00",
            "dimm-serial-number": b"ABCD1234\x00EFGH5678\x00",
            "dimm-speeds": b"2667MHz\x002667MHz\x00",
            "dimm-types": b"DDR4\x00DDR4\x00",
            "ecc-enabled": False,
            "slot-names": b"DIMM0/BANK0\x00DIMM1/BANK1\x00",
        }

        ioreg_plist = self._make_ioreg_plist(memory_entry)

        def side_effect(cmd):
            if cmd == ["uname", "-m"]:
                return b"x86_64"
            if cmd[0] == "ioreg":
                return ioreg_plist
            raise FileNotFoundError(f"Unexpected: {cmd}")

        mock_co.side_effect = side_effect

        info = fetch_memory_info()
        assert len(info.modules) == 2
        assert info.modules[0].manufacturer == "Samsung"
        assert info.modules[0].part_number == "M471A1K43CB1-CTD"
        assert info.modules[0].type == "DDR4"
        assert info.modules[0].frequency_mhz == 2667
        assert info.modules[0].capacity.capacity == 8
        assert info.modules[0].slot.channel == "DIMM0"
        assert info.modules[0].slot.bank == "BANK0"

    @patch("hwprobe.core.mac.memory.subprocess.check_output")
    def test_arm_detected_delegates_to_get_arm_ram_info(self, mock_co):
        """When uname returns arm64, fetch_memory_info should use get_arm_ram_info."""
        plist_data = [
            {
                "_items": [
                    {
                        "SPMemoryDataType": "16 GB",
                    }
                ]
            }
        ]

        def side_effect(cmd):
            if cmd == ["uname", "-m"]:
                return b"arm64"
            if cmd[0] == "system_profiler":
                return plistlib.dumps(plist_data, fmt=plistlib.FMT_XML)
            raise FileNotFoundError(f"Unexpected: {cmd}")

        mock_co.side_effect = side_effect

        info = fetch_memory_info()
        assert isinstance(info, MemoryInfo)

    @patch("hwprobe.core.mac.memory.subprocess.check_output")
    def test_ioreg_failure_returns_failed(self, mock_co):
        def side_effect(cmd):
            if cmd == ["uname", "-m"]:
                return b"x86_64"
            raise FileNotFoundError("ioreg not found")

        mock_co.side_effect = side_effect
        info = fetch_memory_info()
        assert info.status.type == StatusType.FAILED

    @patch("hwprobe.core.mac.memory.get_ram_size_from_system_profiler")
    @patch("hwprobe.core.mac.memory.subprocess.check_output")
    def test_system_profiler_failure_falls_back_to_reg(self, mock_co, mock_sp):
        """When system_profiler fails, the reg-based sizes are retained."""
        mock_sp.side_effect = Exception("system_profiler broke")

        memory_entry = {
            "reg": bytes([0x02, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]),
            "dimm-manufacturer": b"Micron\x00",
            "dimm-part-number": b"PART1\x00",
            "dimm-serial-number": b"SN1\x00",
            "dimm-speeds": b"3200MHz\x00",
            "dimm-types": b"DDR4\x00",
            "slot-names": b"DIMM0/BANK0\x00",
        }
        ioreg_plist = plistlib.dumps(
            {
                "IORegistryEntryChildren": [
                    {
                        "IORegistryEntryChildren": [
                            {
                                "IORegistryEntryName": "memory",
                                **memory_entry,
                            }
                        ]
                    }
                ]
            },
            fmt=plistlib.FMT_XML,
        )

        def side_effect(cmd):
            if cmd == ["uname", "-m"]:
                return b"x86_64"
            if cmd[0] == "ioreg":
                return ioreg_plist
            raise FileNotFoundError(f"Unexpected: {cmd}")

        mock_co.side_effect = side_effect

        info = fetch_memory_info()
        assert any("system profiler" in m.lower() for m in info.status.messages)
        # Module should still have data from reg
        assert len(info.modules) == 1

    @patch("hwprobe.core.mac.memory.get_ram_size_from_system_profiler")
    @patch("hwprobe.core.mac.memory.subprocess.check_output")
    def test_return_type_is_memory_info(self, mock_co, mock_sp):
        mock_sp.return_value = []

        memory_entry = {
            "reg": b"\x00" * 16,
        }
        ioreg_plist = plistlib.dumps(
            {
                "IORegistryEntryChildren": [
                    {
                        "IORegistryEntryChildren": [
                            {
                                "IORegistryEntryName": "memory",
                                **memory_entry,
                            }
                        ]
                    }
                ]
            },
            fmt=plistlib.FMT_XML,
        )

        def side_effect(cmd):
            if cmd == ["uname", "-m"]:
                return b"x86_64"
            if cmd[0] == "ioreg":
                return ioreg_plist
            raise FileNotFoundError(f"Unexpected: {cmd}")

        mock_co.side_effect = side_effect

        info = fetch_memory_info()
        assert isinstance(info, MemoryInfo)


# ── BUG: ecc_enabled is always False ─────────────────────────────────────────


class TestECCDetection:
    @patch("hwprobe.core.mac.memory.get_ram_size_from_system_profiler")
    @patch("hwprobe.core.mac.memory.subprocess.check_output")
    def test_ecc_enabled_detected(self, mock_co, mock_sp):
        from hwprobe.models.size_models import Gigabyte

        mock_sp.return_value = [Gigabyte(capacity=32)]

        memory_entry = {
            "reg": bytes([0x08, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]),
            "dimm-manufacturer": b"Samsung\x00",
            "dimm-part-number": b"ECC-PART\x00",
            "dimm-serial-number": b"SN1\x00",
            "dimm-speeds": b"3200MHz\x00",
            "dimm-types": b"DDR4\x00",
            "ecc-enabled": True,
            "slot-names": b"DIMM0/BANK0\x00",
        }
        ioreg_plist = plistlib.dumps(
            {
                "IORegistryEntryChildren": [
                    {
                        "IORegistryEntryChildren": [
                            {
                                "IORegistryEntryName": "memory",
                                **memory_entry,
                            }
                        ]
                    }
                ]
            },
            fmt=plistlib.FMT_XML,
        )

        def side_effect(cmd):
            if cmd == ["uname", "-m"]:
                return b"x86_64"
            if cmd[0] == "ioreg":
                return ioreg_plist
            raise FileNotFoundError(f"Unexpected: {cmd}")

        mock_co.side_effect = side_effect

        info = fetch_memory_info()
        assert len(info.modules) == 1
        assert info.modules[0].supports_ecc is True


# ── BUG: Uneven list lengths cause IndexError ────────────────────────────────


class TestUnevenListLengths:
    """When lists have different lengths, shorter ones should be skipped
    gracefully and both modules should still be appended."""

    @patch("hwprobe.core.mac.memory.get_ram_size_from_system_profiler")
    @patch("hwprobe.core.mac.memory.subprocess.check_output")
    def test_mismatched_list_lengths_still_appends_both(self, mock_co, mock_sp):
        from hwprobe.models.size_models import Gigabyte

        mock_sp.return_value = [Gigabyte(capacity=8)]

        # 2 manufacturers but only 1 of everything else
        memory_entry = {
            "reg": bytes([0x02, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]),
            "dimm-manufacturer": b"Samsung\x00Micron\x00",
            "dimm-part-number": b"PART1\x00",
            "dimm-serial-number": b"SN1\x00",
            "dimm-speeds": b"3200MHz\x00",
            "dimm-types": b"DDR4\x00",
            "slot-names": b"DIMM0/BANK0\x00",
        }
        ioreg_plist = plistlib.dumps(
            {
                "IORegistryEntryChildren": [
                    {
                        "IORegistryEntryChildren": [
                            {
                                "IORegistryEntryName": "memory",
                                **memory_entry,
                            }
                        ]
                    }
                ]
            },
            fmt=plistlib.FMT_XML,
        )

        def side_effect(cmd):
            if cmd == ["uname", "-m"]:
                return b"x86_64"
            if cmd[0] == "ioreg":
                return ioreg_plist
            raise FileNotFoundError(f"Unexpected: {cmd}")

        mock_co.side_effect = side_effect

        info = fetch_memory_info()
        assert len(info.modules) == 2
        assert info.modules[0].manufacturer == "Samsung"
        assert info.modules[0].part_number == "PART1"
        assert info.modules[1].manufacturer == "Micron"
        assert info.modules[1].part_number is None
