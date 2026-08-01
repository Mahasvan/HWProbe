import ctypes
import struct
from ctypes import addressof, py_object

import pytest

from hwprobe.core.windows import display
from hwprobe.interops.win.legacy.constants import (
    STATUS_FAILURE,
    STATUS_INVALID_ARG,
    STATUS_NOK,
    STATUS_OK,
)
from hwprobe.models.display_models import DisplayInfo
from hwprobe.models.status_models import StatusType

# ============================================================
# Helpers
# ============================================================


def deref(ptr, ctype):
    """Dereference a ctypes byref() argument safely."""
    return ctypes.cast(ptr, ctypes.POINTER(ctype)).contents


def build_minimal_edid(name=b"TEST-MONITOR", width_cm=60, height_cm=34):
    """Build a minimal 128-byte EDID for testing."""
    edid = bytearray(128)
    # decoded: vendor = TST
    vendor = (1 << 10) | (2 << 5) | 3

    edid[8:10] = struct.pack(">H", vendor)
    edid[10:12] = struct.pack("<H", 0x1234)
    edid[12:16] = struct.pack("<I", 0xDEADBEEF)
    edid[21] = width_cm
    edid[22] = height_cm
    off = 54
    edid[off : off + 4] = b"\x00\x00\x00\xfc"
    edid[off + 4] = 0x00
    edid[off + 5 : off + 5 + len(name)] = name
    edid[off + 5 + len(name)] = 0x0A
    return bytes(edid), vendor


# ============================================================
# Aspect ratio tests
# ============================================================


class TestAspectRatios:
    @pytest.mark.parametrize(
        "width,height,real,friendly",
        [
            (3440, 1440, "43:18", "21:9"),
            (1920, 1080, "16:9", "16:9"),
            (1080, 1920, "9:16", "9:16"),
            (5120, 1440, "32:9", "32:9"),
            (1920, 1200, "8:5", "16:10"),
            (1024, 768, "4:3", "4:3"),
            (5120, 768, "20:3", None),
        ],
    )
    def test_common_ratios(self, width, height, real, friendly):
        ratio, r, f = display.get_aspect_ratio(width, height)
        assert r == real
        assert f == friendly
        assert ratio > 0

    @pytest.mark.parametrize(
        "width,height",
        [(0, 1080), (1920, 0), (0, 0)],
    )
    def test_invalid_dimensions(self, width, height):
        ratio, real, friendly = display.get_aspect_ratio(width, height)

        assert ratio is None
        assert real is None
        assert friendly is None


# ============================================================
# EDID parsing tests
# ============================================================


class TestEDIDParsing:
    def test_minimal_edid(self):
        edid, vendor = build_minimal_edid()
        parsed = display.parse_edid(edid)

        assert parsed["manufacturer_code"] == "ABC"
        assert parsed["vendor_id"] == vendor
        assert parsed["product_id"] == 0x1234
        assert parsed["serial"] == 0xDEADBEEF
        assert parsed["name"] == "TEST-MONITOR"
        assert parsed["inches"] > 0

    def test_missing_name_descriptor(self):
        edid, _ = build_minimal_edid()
        edid = bytearray(edid)
        edid[54:58] = b"\x00\x00\x00\x00"
        parsed = display.parse_edid(bytes(edid))

        assert parsed["name"] is None or parsed["name"] == ""

    def test_invalid_length(self):
        assert display.parse_edid(b"short") is None

    def test_invalid_hdev(self, monkeypatch):
        def mockfail_SetupDiGetClassDevsA(cGuidPtr, enumerator, hwndParent, flags):
            return -1  # simulate failure

        monkeypatch.setattr(display, "SetupDiGetClassDevsA", mockfail_SetupDiGetClassDevsA)

        assert display.get_edid_by_hwid(None) is None

    def test_device_interfaces_enum_fail(self, monkeypatch):
        def mockfail_SetupDiEnumDeviceInterfaces(hDev, devData, cGuidPtr, memberIdx, devIntData):
            return False

        monkeypatch.setattr(display, "SetupDiEnumDeviceInterfaces", mockfail_SetupDiEnumDeviceInterfaces)

        assert display.get_edid_by_hwid(None) is None


# ============================================================
# monitor_enum_proc tests
# ============================================================


@pytest.fixture
def fake_win32(monkeypatch):
    """Mock Win32 API calls for monitor enumeration."""

    def fake_GetMonitorInfoA(hmonitor, mi_ptr):
        mi = deref(mi_ptr, display.MONITORINFOEXA)
        mi.szDevice = b"\\\\.\\DISPLAY1"
        return True

    def fake_EnumDisplaySettingsA(device, mode, dm_ptr):
        dm = deref(dm_ptr, display.DEVMODEA)
        dm.dmPelsWidth = 2560
        dm.dmPelsHeight = 1440
        dm.dmDisplayFrequency = 144
        dm.dmDisplayOrientation = 0
        return True

    def fake_EnumDisplayDevicesA(device, idx, dd_ptr, flags):
        dd = deref(dd_ptr, display.DISPLAY_DEVICEA)
        dd.DeviceID = b"MONITOR\\AG326UD\\{SOME-GUID}"
        return True

    monkeypatch.setattr(display, "GetMonitorInfoA", fake_GetMonitorInfoA)
    monkeypatch.setattr(display, "EnumDisplaySettingsA", fake_EnumDisplaySettingsA)
    monkeypatch.setattr(display, "EnumDisplayDevicesA", fake_EnumDisplayDevicesA)


class TestMonitorEnumProc:
    def test_happy_path(self, fake_win32, monkeypatch):
        monitors = DisplayInfo()
        monitors_ptr = py_object(monitors)
        lparam = addressof(monitors_ptr)

        monkeypatch.setattr(display, "find_monitor_gpu", lambda name: ("GPU-0", STATUS_OK))
        monkeypatch.setattr(
            display,
            "get_edid_by_hwid",
            lambda hwid: {
                "name": "AG326UD",
                "vendor_id": 0x1234,
                "product_id": 0x5678,
                "serial": "42",
                "inches": 32,
                "manufacturer_code": "TST",
            },
        )

        ret = display.monitor_enum_proc(1, 0, None, lparam)
        assert ret is True
        assert len(monitors.modules) == 1

        mod = monitors.modules[0]
        assert mod.name == "AG326UD"
        assert mod.gpu_name == "GPU-0"
        assert mod.resolution.width == 2560
        assert mod.resolution.height == 1440
        assert mod.resolution.refresh_rate == 144
        assert int(mod.vendor_id, 16) == 0x1234
        assert int(mod.product_id, 16) == 0x5678
        assert mod.serial_number == "42"
        assert mod.manufacturer_code == "TST"

    def test_no_edid_found(self, fake_win32, monkeypatch):
        monitors = DisplayInfo()
        monitors_ptr = py_object(monitors)
        lparam = addressof(monitors_ptr)

        monkeypatch.setattr(display, "find_monitor_gpu", lambda name: (None, STATUS_NOK))
        monkeypatch.setattr(display, "get_edid_by_hwid", lambda hwid: None)

        ret = display.monitor_enum_proc(1, 0, None, lparam)
        assert ret is True
        assert len(monitors.modules) == 1
        assert monitors.modules[0].name is None

    def test_enum_display_settings_fail(self, monkeypatch):
        def fake_EnumDisplaySettingsA(device, mode, dm_ptr):
            return False

        monitors = DisplayInfo()
        monitors_ptr = py_object(monitors)
        lparam = addressof(monitors_ptr)

        monkeypatch.setattr(display, "EnumDisplaySettingsA", fake_EnumDisplaySettingsA)

        ret = display.monitor_enum_proc(1, 0, None, lparam)

        assert ret is True
        assert monitors.status.type == StatusType.PARTIAL
        assert monitors.modules == []


class TestDisplayInfoFetch:
    def test_fetch_display_info_internal_real(self):
        monitors = display.fetch_display_info_internal()

        assert monitors.status.type == StatusType.SUCCESS
        assert len(monitors.modules) > 0

        module = monitors.modules[0]
        assert module.name is not None
        assert module.gpu_name is not None
        assert module.device_id is not None
        assert module.acpi_path is not None
        assert module.resolution.width > 0
        assert module.resolution.height > 0
        assert module.resolution.aspect_ratio > 0
        assert module.resolution.aspect_ratio_real is not None
        assert module.resolution.aspect_ratio_friendly is not None
        assert module.orientation != "Unknown"
        assert module.inches > 0
        assert module.vendor_id is not None
        assert module.product_id is not None
        assert module.serial_number is not None
        assert module.manufacturer_code is not None

    def test_fetch_display_info_internal_failure(self, monkeypatch):
        def mockfail_EnumDisplayMonitors(hdc, lprcClip, lpfnEnum, dwData):
            return False

        monkeypatch.setattr(display, "EnumDisplayMonitors", mockfail_EnumDisplayMonitors)

        assert display.fetch_display_info_internal().status.type == StatusType.FAILED

    @pytest.mark.parametrize(
        "orientation, expected",
        [
            (0, "Landscape"),
            (1, "Portrait"),
            (2, "Landscape (flipped)"),
            (3, "Portrait (flipped)"),
            (-1, "Unknown"),
        ],
    )
    def test_fetch_display_info_internal_orientations(self, orientation, expected, monkeypatch):
        def fake_EnumDisplaySettingsA(device, mode, dm_ptr):
            dm = deref(dm_ptr, display.DEVMODEA)
            dm.dmPelsWidth = 2560
            dm.dmPelsHeight = 1440
            dm.dmDisplayFrequency = 144
            dm.dmDisplayOrientation = orientation

            return True

        monkeypatch.setattr(display, "EnumDisplaySettingsA", fake_EnumDisplaySettingsA)

        data = display.fetch_display_info_internal()

        assert data.status.type == StatusType.SUCCESS
        assert data.modules[0].orientation.lower() == expected.lower()

    def test_fetch_display_info_internal_missing_pnp(self, monkeypatch):
        def fake_EnumDisplayDevicesA(device, idx, dd_ptr, flags):
            dd = deref(dd_ptr, display.DISPLAY_DEVICEA)
            dd.DeviceID = b""

            return True

        monkeypatch.setattr(display, "EnumDisplayDevicesA", fake_EnumDisplayDevicesA)

        data = display.fetch_display_info_internal()

        assert data.status.type == StatusType.FAILED
        assert data.status.messages[0] == "Failed to fetch Display device information, PNPDeviceID is empty!"


class TestGPU:
    """Coverage for GPU helper method: GetGPUForDisplay(...)"""

    @pytest.mark.parametrize(
        "enc_name, out_buf, buf_size, exp_status",
        [
            (b"\\\\.\\DISPLAY1", ctypes.create_string_buffer(256), 256, STATUS_OK),
            (b"", ctypes.create_string_buffer(256), 256, STATUS_INVALID_ARG),
            (b"\\\\.\\DISPLAY1", None, 256, STATUS_INVALID_ARG),
            (
                b"\\\\.\\DISPLAY1",
                ctypes.create_string_buffer(256),
                0,
                STATUS_INVALID_ARG,
            ),
            (
                b"\\\\.\\DISPLAY420",
                ctypes.create_string_buffer(256),
                256,
                STATUS_FAILURE,
            ),
        ],
    )
    def test_fetch_display_info_gpu_display(self, enc_name, out_buf, buf_size, exp_status, monkeypatch):
        def mock_find_monitor_gpu(device_name):
            res = display.GetGPUForDisplay(enc_name, out_buf, buf_size)
            result = (None, res)

            if res != STATUS_OK:
                return result

            val = out_buf.value.decode("utf-8")

            if val and len(val) > 0:
                result = (val, res)

            return result

        monkeypatch.setattr(display, "find_monitor_gpu", mock_find_monitor_gpu)

        assert display.find_monitor_gpu(enc_name.decode())[1] == exp_status

    @pytest.mark.parametrize(
        "set_status, exp_status",
        [
            (STATUS_NOK, STATUS_NOK),
            (STATUS_INVALID_ARG, STATUS_INVALID_ARG),
            (STATUS_FAILURE, STATUS_FAILURE),
        ],
    )
    def test_fetch_display_info_gpu_display_failures(self, set_status, exp_status, monkeypatch):
        def mockfail_GetGPUForDisplay(enc_name, out_buf, buf_size):
            return set_status  # Simulate failure

        monkeypatch.setattr(display, "GetGPUForDisplay", mockfail_GetGPUForDisplay)

        data = display.find_monitor_gpu("Empty")

        assert data[1] == exp_status
