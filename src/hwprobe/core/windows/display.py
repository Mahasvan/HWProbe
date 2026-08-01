"""
Windows Display Information Module

This module provides functionality to enumerate and collect detailed information
about display monitors on Windows systems. It uses Windows SetupAPI and display
enumeration APIs to gather:
- Display resolution, refresh rate, and orientation
- EDID (Extended Display Identification Data) information
- Connection type (HDMI, DisplayPort, etc.)
- GPU association for each display
"""

import ctypes
import struct
from ctypes import wintypes
from typing import Optional

from hwprobe.core.windows.win_enum import DISPLAY_CON_TYPE

# todo: refactor to new bindings
from hwprobe.interops.win.legacy.constants import (
    DICS_FLAG_GLOBAL,
    DIGCF_DEVICEINTERFACE,
    DIGCF_PRESENT,
    DIREG_DEV,
    DMDO_90,
    DMDO_180,
    DMDO_270,
    DMDO_DEFAULT,
    ENUM_CURRENT_SETTINGS,
    GUID_DEVINTERFACE_MONITOR,
    KEY_READ,
    STATUS_OK,
)
from hwprobe.interops.win.legacy.signatures import (
    EnumDisplayDevicesA,
    EnumDisplayMonitors,
    EnumDisplaySettingsA,
    GetDisplayPathInfo,
    GetGPUForDisplay,
    GetMonitorInfoA,
    RegCloseKey,
    RegQueryValueExA,
    SetupDiDestroyDeviceInfoList,
    SetupDiEnumDeviceInterfaces,
    SetupDiGetClassDevsA,
    SetupDiGetDeviceInterfaceDetailA,
    SetupDiOpenDevRegKey,
)
from hwprobe.interops.win.legacy.structs import (
    DEVMODEA,
    DISPLAY_DEVICEA,
    MONITORENUMPROC,
    MONITORINFOEXA,
    SP_DEVICE_INTERFACE_DATA,
    SP_DEVINFO_DATA,
)
from hwprobe.models.display_models import DisplayInfo, DisplayModuleInfo
from hwprobe.models.status_models import Status, StatusType

# =============================================================================
# Constants
# =============================================================================

# EDID structure constants
_EDID_MIN_LENGTH = 128
_EDID_VENDOR_OFFSET = 8
_EDID_PRODUCT_OFFSET = 10
_EDID_DESCRIPTOR_BASE_OFFSET = 0x48
_EDID_DESCRIPTOR_SIZE = 18
_EDID_DESCRIPTOR_COUNT = 3
_EDID_WIDTH_CM_OFFSET = 21
_EDID_HEIGHT_CM_OFFSET = 22

# EDID descriptor type markers
_EDID_SERIAL_MARKER = b"\x00\x00\x00\xff"
_EDID_NAME_MARKER = b"\x00\x00\x00\xfc"

# Orientation display names
_ORIENTATION_NAMES = {
    DMDO_DEFAULT: "Landscape",
    DMDO_90: "Portrait",
    DMDO_180: "Landscape (flipped)",
    DMDO_270: "Portrait (flipped)",
}

# Invalid registry key handle
_INVALID_HKEY = -1


# =============================================================================
# Utility Functions
# =============================================================================


def _compute_gcd(a: int, b: int) -> int:
    """Compute the greatest common divisor of two integers using Euclidean algorithm."""
    while b:
        a, b = b, a % b
    return a


def get_aspect_ratio(width: int, height: int) -> tuple[Optional[int], Optional[int]]:
    """
    Calculate the aspect ratio for given dimensions.

    Args:
        width: Display width in pixels
        height: Display height in pixels

    Returns:
        A tuple of (width_ratio, height_ratio), e.g., (16, 9) for 1920x1080.
        Returns (None, None) if either dimension is zero.

    Examples:
        >>> get_aspect_ratio(1920, 1080)
        (16, 9)
        >>> get_aspect_ratio(3440, 1440)
        (43, 18)
    """
    if width == 0 or height == 0:
        return None, None

    gcd = _compute_gcd(width, height)
    return width // gcd, height // gcd


def parse_connector_info(connector_info_string: str) -> Optional[dict]:
    """
    Parse connector information string into a structured dictionary.

    The connector info string format (from interop DLL):
        "DisplayID=\\\\.\\DISPLAY1|DisplayPath=\\\\?\\DISPLAY#...|OutputTechnology=5\\n
         DisplayID=\\\\.\\DISPLAY2|DisplayPath=\\\\?\\DISPLAY#...|OutputTechnology=10"

    Args:
        connector_info_string: Raw connector info string with newline-separated devices

    Returns:
        Dictionary mapping display IDs to their properties:
        {
            "\\\\.\\DISPLAY1": {"DisplayPath": "...", "OutputTechnology": "5"},
            "\\\\.\\DISPLAY2": {"DisplayPath": "...", "OutputTechnology": "10"}
        }
        Returns None if parsing fails.
    """
    result = {}

    try:
        devices = connector_info_string.split("\n")

        for device in devices:
            if not device.strip():
                continue

            parts = device.split("|")
            current_display_id = None

            for part in parts:
                if "=" not in part:
                    continue

                key, value = part.split("=", 1)

                if key == "DisplayID":
                    current_display_id = value
                    result[current_display_id] = {}
                elif current_display_id is not None:
                    result[current_display_id][key] = value

    except (ValueError, AttributeError):
        return None

    return result


# =============================================================================
# EDID Parsing
# =============================================================================


def _extract_descriptor_text(descriptor: bytes, marker: bytes) -> Optional[str]:
    """
    Extract text from an EDID descriptor block if it matches the given marker.

    Args:
        descriptor: 18-byte EDID descriptor block
        marker: 4-byte marker identifying the descriptor type

    Returns:
        Decoded and stripped text, or None if marker doesn't match or text is empty.
    """
    if descriptor[0:4] != marker:
        return None

    try:
        # Text data starts at byte 5, terminated by 0x0A (newline)
        raw_text = descriptor[5:18].split(b"\x0a")[0]
        text = raw_text.decode(errors="ignore").strip()
        return text if text else None
    except Exception:
        return None


def _decode_manufacturer_code(vendor_id: int) -> str:
    """
    Decode the 3-letter manufacturer code from EDID vendor ID.

    EDID vendor IDs encode three 5-bit characters (A=1, B=2, etc.) packed into 16 bits.

    Args:
        vendor_id: 16-bit vendor identifier from EDID

    Returns:
        Three-letter manufacturer code (e.g., "SAM" for Samsung, "DEL" for Dell)
    """
    char1 = chr(((vendor_id >> 10) & 0x1F) + ord("A") - 1)
    char2 = chr(((vendor_id >> 5) & 0x1F) + ord("A") - 1)
    char3 = chr((vendor_id & 0x1F) + ord("A") - 1)
    return f"{char1}{char2}{char3}"


def _calculate_diagonal_inches(width_cm: int, height_cm: int) -> float:
    """
    Calculate diagonal screen size in inches from physical dimensions.

    Args:
        width_cm: Physical width in centimeters
        height_cm: Physical height in centimeters

    Returns:
        Diagonal size in inches, rounded to nearest integer. Returns 0 if dimensions invalid.
    """
    if width_cm <= 0 or height_cm <= 0:
        return 0.0

    diagonal_cm = (width_cm**2 + height_cm**2) ** 0.5
    return round(diagonal_cm / 2.54)


def parse_edid(edid: bytes) -> Optional[dict]:
    """
    Parse EDID (Extended Display Identification Data) binary data.

    EDID is a standard data format that displays use to describe their capabilities
    to connected devices. This function extracts commonly needed identification info.

    Args:
        edid: Raw EDID bytes (minimum 128 bytes for base EDID block)

    Returns:
        Dictionary containing:
        - manufacturer_code: 3-letter PNP ID (e.g., "SAM", "DEL")
        - vendor_id: Numeric vendor identifier
        - product_id: Numeric product identifier
        - serial: Serial number string (if present in descriptors)
        - name: Display model name (if present in descriptors)
        - inches: Diagonal screen size in inches

        Returns None if EDID data is too short.
    """
    if len(edid) < _EDID_MIN_LENGTH:
        return None

    # Parse vendor and product IDs
    vendor_id = struct.unpack(">H", edid[_EDID_VENDOR_OFFSET : _EDID_VENDOR_OFFSET + 2])[0]
    product_id = struct.unpack("<H", edid[_EDID_PRODUCT_OFFSET : _EDID_PRODUCT_OFFSET + 2])[0]

    serial = None
    name = None

    # Parse descriptor blocks to find serial number and display name
    # First descriptor (at 0x36) is reserved for Preferred Timing Mode, so we start at 0x48
    for i in range(_EDID_DESCRIPTOR_COUNT):
        offset = _EDID_DESCRIPTOR_BASE_OFFSET + (i * _EDID_DESCRIPTOR_SIZE)
        descriptor = edid[offset : offset + _EDID_DESCRIPTOR_SIZE]

        if serial is None:
            serial = _extract_descriptor_text(descriptor, _EDID_SERIAL_MARKER)

        if name is None:
            name = _extract_descriptor_text(descriptor, _EDID_NAME_MARKER)

    return {
        "manufacturer_code": _decode_manufacturer_code(vendor_id),
        "vendor_id": vendor_id,
        "product_id": product_id,
        "serial": serial,
        "name": name,
        "inches": _calculate_diagonal_inches(edid[_EDID_WIDTH_CM_OFFSET], edid[_EDID_HEIGHT_CM_OFFSET]),
    }


def uniquely_identify_display_path(display_path: str) -> Optional[str]:
    """
    Extract the serial number from a display path for unique identification.

    Args:
        display_path: Display path string (e.g., "\\\\?\\DISPLAY#MANUF#...")

    Returns:
        Serial number string if found, None otherwise.
    """
    edid = get_edid_by_hwid(display_path)
    return edid.get("serial") if edid else None


# =============================================================================
# GPU and Display Association
# =============================================================================


def find_monitor_gpu(device_name: str) -> tuple[Optional[str], int]:
    """
    Find the GPU that a monitor is connected to.

    Args:
        device_name: Display device name (e.g., "\\\\.\\DISPLAY1")

    Returns:
        Tuple of (gpu_name, status_code):
        - gpu_name: Name of the GPU, or None if not found
        - status_code: API result code (STATUS_OK on success)
    """
    buffer = ctypes.create_string_buffer(256)
    encoded_name = device_name.encode("utf-8")

    result_code = GetGPUForDisplay(encoded_name, buffer, 256)

    if result_code != STATUS_OK:
        return None, result_code

    gpu_name = buffer.value.decode("utf-8")
    return (gpu_name if gpu_name else None), result_code


# =============================================================================
# Registry EDID Lookup
# =============================================================================


def _get_device_interface_detail_size() -> int:
    """Get the correct cbSize value for SP_DEVICE_INTERFACE_DETAIL_DATA based on architecture."""
    return 8 if ctypes.sizeof(ctypes.c_void_p) == 8 else 6


def _read_edid_from_registry(hkey) -> Optional[dict]:
    """
    Read and parse EDID data from an open registry key.

    Args:
        hkey: Open registry key handle for a monitor device

    Returns:
        Parsed EDID dictionary, or None if read fails.
    """
    edid_size = wintypes.DWORD()

    # Query EDID value size first
    if RegQueryValueExA(hkey, b"EDID", None, None, None, ctypes.byref(edid_size)) != 0:
        return None

    # Read the actual EDID data
    edid_buffer = (ctypes.c_ubyte * edid_size.value)()
    if RegQueryValueExA(hkey, b"EDID", None, None, edid_buffer, ctypes.byref(edid_size)) != 0:
        return None

    return parse_edid(bytes(edid_buffer))


def _extract_device_path(detail_buffer) -> str:
    """Extract the device path string from a device interface detail buffer."""
    path_offset = ctypes.sizeof(wintypes.DWORD)
    raw_path = ctypes.string_at(ctypes.addressof(detail_buffer) + path_offset)
    return raw_path.decode("ascii", errors="ignore").upper()


def get_edid_by_hwid(hwid: str) -> Optional[dict]:
    """
    Fetch EDID data from the Windows registry for a specific display device.

    Uses Windows SetupAPI to enumerate monitor device interfaces and find
    the one matching the given hardware ID, then reads its EDID from registry.

    Args:
        hwid: Hardware ID to match. Can be in formats like:
            - "MONITOR\\AG326UD\\{...}"
            - "\\\\?\\DISPLAY#MANUF#..."

    Returns:
        Parsed EDID dictionary containing manufacturer_code, vendor_id, product_id,
        serial, name, and inches. Returns None if not found or on error.
    """
    if not hwid:
        return None

    hwid_upper = hwid.upper()

    # Get device information set for monitor interfaces
    device_info_set = SetupDiGetClassDevsA(
        ctypes.byref(GUID_DEVINTERFACE_MONITOR),
        None,
        None,
        DIGCF_PRESENT | DIGCF_DEVICEINTERFACE,
    )

    if device_info_set == _INVALID_HKEY:
        return None

    try:
        return _enumerate_and_find_edid(device_info_set, hwid_upper)
    finally:
        SetupDiDestroyDeviceInfoList(device_info_set)


def _enumerate_and_find_edid(device_info_set, hwid_upper: str) -> Optional[dict]:
    """
    Enumerate device interfaces and find EDID for matching hardware ID.

    Args:
        device_info_set: Handle to device information set
        hwid_upper: Uppercase hardware ID to match

    Returns:
        Parsed EDID dictionary if found, None otherwise.
    """
    interface_index = 0

    while True:
        interface_data = SP_DEVICE_INTERFACE_DATA()
        interface_data.cbSize = ctypes.sizeof(SP_DEVICE_INTERFACE_DATA)

        # Enumerate next interface
        if not SetupDiEnumDeviceInterfaces(
            device_info_set,
            None,
            ctypes.byref(GUID_DEVINTERFACE_MONITOR),
            interface_index,
            ctypes.byref(interface_data),
        ):
            break

        edid = _try_get_edid_for_interface(device_info_set, interface_data, hwid_upper)
        if edid is not None:
            return edid

        interface_index += 1

    return None


def _try_get_edid_for_interface(device_info_set, interface_data, hwid_upper: str) -> Optional[dict]:
    """
    Attempt to retrieve EDID for a single device interface if it matches the hardware ID.

    Args:
        device_info_set: Handle to device information set
        interface_data: Device interface data structure
        hwid_upper: Uppercase hardware ID to match

    Returns:
        Parsed EDID dictionary if this interface matches and EDID is readable, None otherwise.
    """
    # Get required buffer size for interface detail
    required_size = wintypes.DWORD(0)
    SetupDiGetDeviceInterfaceDetailA(
        device_info_set,
        ctypes.byref(interface_data),
        None,
        0,
        ctypes.byref(required_size),
        None,
    )

    if required_size.value == 0:
        return None

    # Prepare detail buffer with correct cbSize
    detail_buffer = ctypes.create_string_buffer(required_size.value)
    struct.pack_into("I", detail_buffer, 0, _get_device_interface_detail_size())

    device_data = SP_DEVINFO_DATA()
    device_data.cbSize = ctypes.sizeof(SP_DEVINFO_DATA)

    # Get interface detail and device info
    if not SetupDiGetDeviceInterfaceDetailA(
        device_info_set,
        ctypes.byref(interface_data),
        detail_buffer,
        required_size,
        None,
        ctypes.byref(device_data),
    ):
        return None

    # Check if this device matches our hardware ID
    device_path = _extract_device_path(detail_buffer)
    if hwid_upper not in device_path:
        return None

    # Open registry key and read EDID
    registry_key = SetupDiOpenDevRegKey(
        device_info_set,
        ctypes.byref(device_data),
        DICS_FLAG_GLOBAL,
        0,
        DIREG_DEV,
        KEY_READ,
    )

    if registry_key == _INVALID_HKEY or registry_key == 0:
        return None

    try:
        return _read_edid_from_registry(registry_key)
    finally:
        RegCloseKey(registry_key)


# =============================================================================
# Monitor Enumeration
# =============================================================================


def _get_orientation_name(orientation_code: int) -> str:
    """Convert Windows display orientation code to human-readable name."""
    return _ORIENTATION_NAMES.get(orientation_code, "Unknown")


def _get_connection_type(connector_info: Optional[dict]) -> Optional[str]:
    """
    Extract connection type name from connector info.

    Args:
        connector_info: Dictionary containing OutputTechnology value

    Returns:
        Human-readable connection type (e.g., "HDMI", "DisplayPort"), or None.
    """
    if not connector_info:
        return None

    try:
        technology_code = int(connector_info.get("OutputTechnology", -2))
        return DISPLAY_CON_TYPE.get(technology_code)
    except (ValueError, TypeError):
        return None


def _fetch_edid_for_monitor(connector_info: Optional[dict], pnp_device_id: str) -> tuple[Optional[dict], Optional[str]]:
    """
    Fetch EDID data for a monitor, preferring display path over PNP ID.

    Args:
        connector_info: Connector info dict with DisplayPath (may be None)
        pnp_device_id: PNP device ID as fallback

    Returns:
        Tuple of (edid_dict, device_path) where device_path may be None.
    """
    device_path = None

    # Prefer display path for more accurate EDID matching
    if connector_info:
        device_path = connector_info.get("DisplayPath")
        if device_path:
            edid = get_edid_by_hwid(device_path)
            if edid:
                return edid, device_path

    # Fallback to PNP device ID
    if pnp_device_id:
        parts = pnp_device_id.split("\\")
        if len(parts) > 1:
            edid = get_edid_by_hwid(parts[1])
            return edid, device_path

    return None, device_path


def _build_monitor_info(
    device_id: str,
    hardware_id: str,
    device_path: Optional[str],
    display_mode: DEVMODEA,
    edid: Optional[dict],
    gpu_name: Optional[str],
    connection_type: Optional[str],
) -> DisplayModuleInfo:
    """
    Construct a DisplayModuleInfo object from collected data.

    Args:
        device_id: Display device identifier (e.g., "\\\\.\\DISPLAY1")
        hardware_id: PNP hardware ID
        device_path: Display path string (may be None)
        display_mode: DEVMODEA structure with current display settings
        edid: Parsed EDID dictionary (may be None)
        gpu_name: Name of associated GPU (may be None)
        connection_type: Connection type string (may be None)

    Returns:
        Populated DisplayModuleInfo object.
    """
    monitor = DisplayModuleInfo()

    # Basic identification
    monitor.device_id = device_id
    monitor.acpi_path = hardware_id
    monitor.device_path = device_path
    monitor.gpu_name = gpu_name
    monitor.interface = connection_type

    # Resolution info
    monitor.resolution.width = display_mode.dmPelsWidth
    monitor.resolution.height = display_mode.dmPelsHeight
    monitor.resolution.refresh_rate = display_mode.dmDisplayFrequency
    monitor.resolution.aspect_ratio = get_aspect_ratio(display_mode.dmPelsWidth, display_mode.dmPelsHeight)

    # Orientation
    monitor.orientation = _get_orientation_name(display_mode.dmDisplayOrientation)

    # EDID-derived information
    if edid:
        monitor.name = edid.get("name")
        monitor.inches = edid.get("inches")
        monitor.manufacturer_code = edid.get("manufacturer_code")
        monitor.serial_number = str(edid["serial"]) if edid.get("serial") is not None else None
        monitor.vendor_id = f"0x{edid['vendor_id']:04X}" if edid.get("vendor_id") else None
        monitor.product_id = f"0x{edid['product_id']:04X}" if edid.get("product_id") else None

    return monitor


def _add_partial_status(display_info: DisplayInfo, message: str) -> None:
    """Add a partial status message to the display info."""
    display_info.status = Status(type=StatusType.PARTIAL)
    display_info.status.messages.append(message)


def _monitor_enum_callback(hmonitor, hdc, rect, lparam) -> bool:
    """
    Callback function for EnumDisplayMonitors.

    Called for each active monitor. Collects display information and adds
    it to the DisplayInfo list passed via lparam.

    Args:
        hmonitor: Handle to the display monitor
        hdc: Handle to device context (unused)
        rect: Pointer to RECT with monitor coordinates (unused)
        lparam: Pointer to DisplayInfo object being populated

    Returns:
        True to continue enumeration, False to stop.
    """
    # Retrieve the DisplayInfo object from the pointer
    display_info_ptr = ctypes.cast(lparam, ctypes.POINTER(ctypes.py_object))
    display_info: DisplayInfo = display_info_ptr.contents.value

    # Get monitor info including device name
    monitor_info = MONITORINFOEXA()
    monitor_info.cbSize = ctypes.sizeof(monitor_info)
    GetMonitorInfoA(hmonitor, ctypes.byref(monitor_info))

    device_id = monitor_info.szDevice.decode()
    if not device_id:
        _add_partial_status(display_info, "Failed to fetch Display device information, DeviceID is empty!")
        return True

    # Get current display settings
    display_mode = DEVMODEA()
    display_mode.dmSize = ctypes.sizeof(display_mode)
    EnumDisplaySettingsA(monitor_info.szDevice, ENUM_CURRENT_SETTINGS, ctypes.byref(display_mode))

    # Get PNP device ID
    display_device = DISPLAY_DEVICEA(cb=ctypes.sizeof(DISPLAY_DEVICEA))
    EnumDisplayDevicesA(monitor_info.szDevice, 0, ctypes.byref(display_device), 0)
    pnp_device_id = display_device.DeviceID.decode()

    if not pnp_device_id:
        _add_partial_status(display_info, "Failed to fetch Display device information, PNPDeviceID is empty!")
        return True

    # Get connector info for this display
    connector_info_map = getattr(display_info, "_connectorInfo", None)
    connector_info = connector_info_map.get(device_id) if connector_info_map else None

    # Get GPU association
    gpu_name, gpu_result_code = find_monitor_gpu(device_id)

    # Get EDID and connection type
    edid, device_path = _fetch_edid_for_monitor(connector_info, pnp_device_id)
    connection_type = _get_connection_type(connector_info)

    # Build and add monitor info
    monitor = _build_monitor_info(
        device_id=device_id,
        hardware_id=pnp_device_id,
        device_path=device_path,
        display_mode=display_mode,
        edid=edid,
        gpu_name=gpu_name if gpu_result_code == STATUS_OK else None,
        connection_type=connection_type,
    )

    display_info.modules.append(monitor)
    return True


# Keep the original name for backward compatibility
monitor_enum_proc = _monitor_enum_callback


# =============================================================================
# Public API
# =============================================================================


def _fetch_connector_info() -> tuple[Optional[dict], Optional[tuple[StatusType, str]]]:
    """
    Fetch display connector information from the interop DLL.

    Returns:
        Tuple of (connector_info_dict, error_info):
        - connector_info_dict: Parsed connector info, or None on failure
        - error_info: Tuple of (StatusType, message) if failed, None on success
    """
    buffer = ctypes.create_string_buffer(4096)
    result_code = GetDisplayPathInfo(buffer, 4096)

    if result_code != STATUS_OK:
        return None, (StatusType.PARTIAL, f"Failed to fetch Display connector information, error code: {result_code}")

    raw_string = buffer.value.decode("utf-8", errors="ignore").strip()
    return parse_connector_info(raw_string), None


def fetch_display_info_internal() -> DisplayInfo:
    """
    Enumerate all display monitors and collect their information.

    This is the main entry point for display enumeration. It:
    1. Fetches connector information from the interop DLL
    2. Enumerates all active monitors using EnumDisplayMonitors
    3. For each monitor, collects resolution, EDID data, GPU association, etc.

    Returns:
        DisplayInfo object containing a list of DisplayModuleInfo objects,
        one per detected monitor, along with status information.
    """
    display_info = DisplayInfo()

    # Fetch connector information (display paths and connection types)
    connector_info, error = _fetch_connector_info()
    if error:
        display_info.status.type = error[0]
        display_info.status.messages.append(error[1])
    else:
        display_info._connectorInfo = connector_info

    # Enumerate all monitors
    display_info_ptr = ctypes.py_object(display_info)
    enum_callback = MONITORENUMPROC(_monitor_enum_callback)

    EnumDisplayMonitors(0, 0, enum_callback, ctypes.addressof(display_info_ptr))

    # Mark as failed if no monitors were found
    if len(display_info.modules) == 0:
        display_info.status.type = StatusType.FAILED

    return display_info
