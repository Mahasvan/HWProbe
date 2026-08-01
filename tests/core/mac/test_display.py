import json
from unittest.mock import MagicMock, patch

from hwprobe.core.mac.display import (
    _enrich_data_from_edid,
    _fetch_monitor_info_system_profiler,
    _get_monitor_resolution_from_system_profiler,
    _get_refresh_rate_from_system_profiler,
    fetch_display_info,
)
from hwprobe.models.display_models import DisplayModuleInfo
from hwprobe.models.status_models import StatusType

# ── sample system_profiler JSON structures ───────────────────────────────────


def _make_sp_output(monitors_per_controller=None):
    """Build a fake system_profiler SPDisplaysDataType JSON structure."""
    if monitors_per_controller is None:
        monitors_per_controller = [
            [
                {
                    "_name": "Built-in Retina Display",
                    "spdisplays_pixelresolution": "3024 x 1964 @ 120.00Hz",
                    "_spdisplays_display-serial-number": "SN12345",
                    "_spdisplays_display-year": "2023",
                    "sppci_model": "Apple M3 Pro",
                }
            ]
        ]

    controllers = []
    for i, monitors in enumerate(monitors_per_controller):
        controllers.append(
            {
                "_name": f"Controller {i}",
                "sppci_model": f"GPU {i}",
                "spdisplays_ndrvs": monitors,
            }
        )

    return {"SPDisplaysDataType": controllers}


def _make_subprocess_run_mock(sp_output):
    """Return a mock for subprocess.run that returns the given JSON."""
    mock_result = MagicMock()
    mock_result.stdout = json.dumps(sp_output)
    mock_run = MagicMock(return_value=mock_result)
    return mock_run


# ── _get_monitor_resolution_from_system_profiler ─────────────────────────────


class TestGetMonitorResolution:
    def test_pixelresolution_key(self):
        monitor = {"spdisplays_pixelresolution": "3024 x 1964 @ 120.00Hz"}
        result = _get_monitor_resolution_from_system_profiler(monitor)
        assert result == (3024, 1964)

    def test_resolution_key(self):
        monitor = {"spdisplays_resolution": "1920 x 1080"}
        result = _get_monitor_resolution_from_system_profiler(monitor)
        assert result == (1920, 1080)

    def test_underscore_resolution_key(self):
        monitor = {"_spdisplays_resolution": "2560x1440"}
        result = _get_monitor_resolution_from_system_profiler(monitor)
        assert result == (2560, 1440)

    def test_pixels_key(self):
        monitor = {"_spdisplays_pixels": "3840 x 2160"}
        result = _get_monitor_resolution_from_system_profiler(monitor)
        assert result == (3840, 2160)

    def test_precedence_order(self):
        """pixelresolution should win over resolution."""
        monitor = {
            "spdisplays_pixelresolution": "3024 x 1964",
            "spdisplays_resolution": "1512 x 982",
        }
        result = _get_monitor_resolution_from_system_profiler(monitor)
        assert result == (3024, 1964)

    def test_no_resolution_keys_returns_none(self):
        monitor = {"_name": "Some Monitor"}
        result = _get_monitor_resolution_from_system_profiler(monitor)
        assert result is None

    def test_no_digits_in_value_returns_none(self):
        monitor = {"spdisplays_pixelresolution": "Unknown"}
        result = _get_monitor_resolution_from_system_profiler(monitor)
        assert result is None


# ── _get_refresh_rate_from_system_profiler ───────────────────────────────────


class TestGetRefreshRate:
    def test_refresh_rate_from_pixelresolution(self):
        monitor = {"spdisplays_pixelresolution": "3024 x 1964 @ 120.00Hz"}
        result = _get_refresh_rate_from_system_profiler(monitor)
        assert result == 120.0

    def test_refresh_rate_from_spdisplays_resolution(self):
        monitor = {"spdisplays_resolution": "1920 x 1080 @ 60Hz"}
        result = _get_refresh_rate_from_system_profiler(monitor)
        assert result == 60.0

    def test_refresh_rate_from_underscore_resolution(self):
        monitor = {"_spdisplays_resolution": "2560 x 1440 @ 144Hz"}
        result = _get_refresh_rate_from_system_profiler(monitor)
        assert result == 144.0

    def test_no_refresh_rate_returns_none(self):
        monitor = {"spdisplays_resolution": "1920 x 1080"}
        result = _get_refresh_rate_from_system_profiler(monitor)
        assert result is None

    def test_fractional_refresh_rate(self):
        monitor = {"_spdisplays_resolution": "3840 x 2160 @ 59.94Hz"}
        result = _get_refresh_rate_from_system_profiler(monitor)
        assert result == 59.94

    def test_refresh_rate_from_underscore_pixels_key(self):
        monitor = {"_spdisplays_pixels": "3024 x 1964 @ 120Hz"}
        result = _get_refresh_rate_from_system_profiler(monitor)
        assert result == 120.0


# ── _enrich_data_from_edid ───────────────────────────────────────────────────


class TestEnrichDataFromEdid:
    def test_hex_prefix_stripped(self):
        """EDID strings starting with 0x should have the prefix removed."""
        monitor = DisplayModuleInfo()
        # Minimal valid-ish 128-byte EDID (all zeros except header)
        edid_hex = "00" * 128
        # Should not crash
        result = _enrich_data_from_edid(monitor, "0x" + edid_hex)
        assert isinstance(result, DisplayModuleInfo)

    def test_without_hex_prefix(self):
        monitor = DisplayModuleInfo()
        edid_hex = "00" * 128
        result = _enrich_data_from_edid(monitor, edid_hex)
        assert isinstance(result, DisplayModuleInfo)

    def test_existing_fields_not_overwritten(self):
        """Fields already set on monitor_info should not be overwritten by EDID data."""
        monitor = DisplayModuleInfo()
        monitor.name = "My Custom Name"
        edid_hex = "00" * 128
        result = _enrich_data_from_edid(monitor, edid_hex)
        assert result.name == "My Custom Name"


# ── _fetch_monitor_info_system_profiler ──────────────────────────────────────


class TestFetchMonitorInfoSystemProfiler:
    @patch("hwprobe.core.mac.display.subprocess.run")
    def test_single_monitor_basic_info(self, mock_run):
        # gpu_name comes from the controller-level sppci_model, not the monitor dict
        sp_data = {
            "SPDisplaysDataType": [
                {
                    "_name": "Controller",
                    "sppci_model": "Apple M3 Pro",
                    "spdisplays_ndrvs": [
                        {
                            "_name": "Built-in Display",
                            "spdisplays_pixelresolution": "3024 x 1964 @ 120.00Hz",
                            "_spdisplays_display-serial-number": "SN123",
                            "_spdisplays_display-year": "2023",
                        }
                    ],
                }
            ]
        }
        mock_result = MagicMock()
        mock_result.stdout = json.dumps(sp_data)
        mock_run.return_value = mock_result

        monitors, status = _fetch_monitor_info_system_profiler()

        assert len(monitors) == 1
        m = monitors[0]
        assert m.name == "Built-in Display"
        assert m.serial_number == "SN123"
        assert m.year == 2023
        assert m.gpu_name == "Apple M3 Pro"
        assert m.resolution is not None
        assert m.resolution.width == 3024
        assert m.resolution.height == 1964

    @patch("hwprobe.core.mac.display.subprocess.run")
    def test_missing_name_is_partial(self, mock_run):
        sp_data = _make_sp_output(
            [
                [
                    {
                        "spdisplays_pixelresolution": "1920 x 1080 @ 60Hz",
                    }
                ]
            ]
        )
        mock_result = MagicMock()
        mock_result.stdout = json.dumps(sp_data)
        mock_run.return_value = mock_result

        monitors, status = _fetch_monitor_info_system_profiler()
        assert len(monitors) == 1
        assert status.type == StatusType.PARTIAL
        assert any("name" in m.lower() for m in status.messages)

    @patch("hwprobe.core.mac.display.subprocess.run")
    def test_missing_serial_is_partial(self, mock_run):
        sp_data = _make_sp_output(
            [
                [
                    {
                        "_name": "Display",
                        "spdisplays_pixelresolution": "1920 x 1080 @ 60Hz",
                    }
                ]
            ]
        )
        mock_result = MagicMock()
        mock_result.stdout = json.dumps(sp_data)
        mock_run.return_value = mock_result

        monitors, status = _fetch_monitor_info_system_profiler()
        assert status.type == StatusType.PARTIAL
        assert any("serial" in m.lower() for m in status.messages)

    @patch("hwprobe.core.mac.display.subprocess.run")
    def test_missing_year_is_partial(self, mock_run):
        sp_data = _make_sp_output(
            [
                [
                    {
                        "_name": "Display",
                        "_spdisplays_display-serial-number": "SN1",
                        "spdisplays_pixelresolution": "1920 x 1080 @ 60Hz",
                    }
                ]
            ]
        )
        mock_result = MagicMock()
        mock_result.stdout = json.dumps(sp_data)
        mock_run.return_value = mock_result

        monitors, status = _fetch_monitor_info_system_profiler()
        assert any("year" in m.lower() for m in status.messages)

    @patch("hwprobe.core.mac.display.subprocess.run")
    def test_missing_gpu_name_is_partial(self, mock_run):
        sp_data = {
            "SPDisplaysDataType": [
                {
                    "spdisplays_ndrvs": [
                        {
                            "_name": "Display",
                            "spdisplays_pixelresolution": "1920 x 1080 @ 60Hz",
                            "_spdisplays_display-serial-number": "SN1",
                            "_spdisplays_display-year": "2023",
                        }
                    ]
                }
            ]
        }
        mock_result = MagicMock()
        mock_result.stdout = json.dumps(sp_data)
        mock_run.return_value = mock_result

        monitors, status = _fetch_monitor_info_system_profiler()
        assert any("GPU" in m for m in status.messages)

    @patch("hwprobe.core.mac.display.subprocess.run")
    def test_empty_sp_output_returns_empty_list(self, mock_run):
        mock_result = MagicMock()
        mock_result.stdout = json.dumps({})
        mock_run.return_value = mock_result

        monitors, status = _fetch_monitor_info_system_profiler()
        assert monitors == []

    @patch("hwprobe.core.mac.display.subprocess.run")
    def test_json_decode_error_returns_empty_list(self, mock_run):
        mock_result = MagicMock()
        mock_result.stdout = "NOT JSON"
        mock_run.return_value = mock_result

        monitors, status = _fetch_monitor_info_system_profiler()
        assert monitors == []

    @patch("hwprobe.core.mac.display.subprocess.run")
    def test_multiple_monitors_across_controllers(self, mock_run):
        sp_data = _make_sp_output(
            [
                [{"_name": "Monitor A", "spdisplays_pixelresolution": "1920 x 1080 @ 60Hz"}],
                [{"_name": "Monitor B", "spdisplays_pixelresolution": "2560 x 1440 @ 144Hz"}],
            ]
        )
        mock_result = MagicMock()
        mock_result.stdout = json.dumps(sp_data)
        mock_run.return_value = mock_result

        monitors, status = _fetch_monitor_info_system_profiler()
        assert len(monitors) == 2
        assert monitors[0].name == "Monitor A"
        assert monitors[1].name == "Monitor B"

    @patch("hwprobe.core.mac.display.subprocess.run")
    def test_edid_enrichment_called_when_present(self, mock_run):
        """When _spdisplays_edid is present, _enrich_data_from_edid is called."""
        # 128 bytes of zeros is a minimal (invalid but parseable) EDID
        edid_hex = "00" * 128
        sp_data = _make_sp_output(
            [
                [
                    {
                        "_name": "External Monitor",
                        "spdisplays_pixelresolution": "3840 x 2160 @ 60Hz",
                        "_spdisplays_display-serial-number": "SN1",
                        "_spdisplays_display-year": "2020",
                        "sppci_model": "AMD GPU",
                        "_spdisplays_edid": edid_hex,
                    }
                ]
            ]
        )
        mock_result = MagicMock()
        mock_result.stdout = json.dumps(sp_data)
        mock_run.return_value = mock_result

        monitors, status = _fetch_monitor_info_system_profiler()
        assert len(monitors) == 1

    @patch("hwprobe.core.mac.display.subprocess.run")
    def test_missing_edid_is_partial(self, mock_run):
        sp_data = _make_sp_output(
            [
                [
                    {
                        "_name": "Display",
                        "spdisplays_pixelresolution": "1920 x 1080 @ 60Hz",
                        "_spdisplays_display-serial-number": "SN1",
                        "_spdisplays_display-year": "2023",
                        "sppci_model": "GPU",
                    }
                ]
            ]
        )
        mock_result = MagicMock()
        mock_result.stdout = json.dumps(sp_data)
        mock_run.return_value = mock_result

        monitors, status = _fetch_monitor_info_system_profiler()
        assert any("EDID" in m for m in status.messages)


# ── fetch_display_info ───────────────────────────────────────────────────────


class TestFetchDisplayInfo:
    @patch("hwprobe.core.mac.display.subprocess.run")
    def test_returns_display_info_type(self, mock_run):
        from hwprobe.models.display_models import DisplayInfo

        sp_data = _make_sp_output()
        mock_result = MagicMock()
        mock_result.stdout = json.dumps(sp_data)
        mock_run.return_value = mock_result

        info = fetch_display_info()
        assert isinstance(info, DisplayInfo)

    @patch("hwprobe.core.mac.display.subprocess.run")
    def test_modules_populated(self, mock_run):
        sp_data = _make_sp_output(
            [
                [
                    {"_name": "A", "spdisplays_pixelresolution": "1920x1080 @ 60Hz"},
                    {"_name": "B", "spdisplays_pixelresolution": "2560x1440 @ 120Hz"},
                ]
            ]
        )
        mock_result = MagicMock()
        mock_result.stdout = json.dumps(sp_data)
        mock_run.return_value = mock_result

        info = fetch_display_info()
        assert len(info.modules) == 2
