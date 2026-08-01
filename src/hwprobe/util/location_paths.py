"""
Thin ctypes wrapper over cfgmgr32.dll device-node properties.

Public API (used by core/windows/graphics.py and core/windows/network.py):
    get_location_paths(pnp_device_id) -> list[str] | None
    fetch_pcie_info(pnp_device_id)   -> (speed, width) | None

Internal: one _get_devnode_property(pnp_id, key) -> bytes | None handles the
two-call buffer sizing pattern. Decoders for string-list and uint32 are
module-level. DEVPROPKEY constants are built once at import, not per call.
"""

from ctypes import Structure, WinDLL, byref, c_buffer, c_char, c_ulong, c_ushort, c_wchar_p, sizeof
from typing import Optional

_cfgmgr = WinDLL("cfgmgr32.dll")

# ---- ctypes structs (built once) ----


class GUID(Structure):
    _fields_ = [
        ("Data1", c_ulong),
        ("Data2", c_ushort),
        ("Data3", c_ushort),
        ("Data4", c_char * 8),
    ]


class DEVPROPKEY(Structure):
    _fields_ = [("fmtid", GUID), ("pid", c_ulong)]


def _key(data1, data2, data3, data4_bytes, pid) -> DEVPROPKEY:
    return DEVPROPKEY(
        fmtid=GUID(Data1=data1, Data2=data2, Data3=data3, Data4=bytes(data4_bytes)),
        pid=pid,
    )


# ---- DEVPROPKEY constants (module-level, built once) ----
# Source: DEVPKEY_Device_LocationPaths, DEVPKEY_Device_BusNumber,
#         DEVPKEY_Device_Address, DEVPKEY_PCIExpress_CurrentLinkSpeed/Width

_LOCATION_PATHS = _key(0xA45C254E, 0xDF1C, 0x4EFD, [0x80, 0x20, 0x67, 0xD1, 0x46, 0xA8, 0x50, 0xE0], 37)
_BUS_NUMBER = _key(0xA45C254E, 0xDF1C, 0x4EFD, [0x80, 0x20, 0x67, 0xD1, 0x46, 0xA8, 0x50, 0xE0], 23)
_DEVICE_ADDRESS = _key(0xA45C254E, 0xDF1C, 0x4EFD, [0x80, 0x20, 0x67, 0xD1, 0x46, 0xA8, 0x50, 0xE0], 30)
_PCIE_LINK_SPEED = _key(0x3AB22E31, 0x8264, 0x4B4E, [0x9A, 0xF5, 0xA8, 0xD2, 0xD8, 0xE3, 0x3E, 0x62], 9)
_PCIE_LINK_WIDTH = _key(0x3AB22E31, 0x8264, 0x4B4E, [0x9A, 0xF5, 0xA8, 0xD2, 0xD8, 0xE3, 0x3E, 0x62], 10)

# CR_SUCCESS = 0, CR_BUFFER_SMALL = 0x1A, CR_NO_SUCH_DEVNODE = 0x02
_CR_SUCCESS = 0
_CR_BUFFER_SMALL = 0x1A


# ---- core: locate devnode + get property (two-call pattern) ----

def _locate_devnode(pnp_device_id: str) -> Optional[c_ulong]:
    """Get the device node instance handle from a PNP Device ID string."""
    dev_node = c_ulong()
    result = _cfgmgr.CM_Locate_DevNodeW(
        byref(dev_node),
        c_wchar_p(pnp_device_id),
        c_ulong(0),  # CM_LOCATE_DEVNODE_NORMAL
    )
    return dev_node if result == _CR_SUCCESS else None


def _get_devnode_property(pnp_device_id: str, prop_key: DEVPROPKEY) -> Optional[bytes]:
    """
    Fetch a raw property buffer from CM_Get_DevNode_PropertyW.
    Two-call pattern: query size, alloc, query data.
    Returns raw bytes or None if the property doesn't exist / lookup fails.
    """
    dn = _locate_devnode(pnp_device_id)
    if dn is None:
        return None

    prop_type = c_ulong()
    buf_size = c_ulong(0)

    # First call: get required buffer size.
    status = _cfgmgr.CM_Get_DevNode_PropertyW(
        dn, byref(prop_key), byref(prop_type), None, byref(buf_size), c_ulong(0)
    )
    if status == _CR_SUCCESS:
        # Property exists with zero-size payload (rare). Return empty.
        return b""
    if status != _CR_BUFFER_SMALL:
        return None  # CR_NO_SUCH_DEVNODE or other failure

    # Second call: fill the buffer.
    buf = c_buffer(buf_size.value)
    status = _cfgmgr.CM_Get_DevNode_PropertyW(
        dn, byref(prop_key), byref(prop_type), buf, byref(buf_size), c_ulong(0)
    )
    if status != _CR_SUCCESS:
        return None
    return buf.raw


# ---- decoders ----

def _decode_string_list(raw: bytes) -> list[str]:
    """Decode a REG_MULTI_SZ-style buffer (UTF-16-LE, NUL-separated strings)."""
    text = raw.decode("utf-16-le", errors="ignore")
    return [p for p in text.split("\x00") if p]


def _decode_uint32(raw: bytes) -> Optional[int]:
    """Decode a 32-bit unsigned integer from little-endian bytes."""
    if len(raw) < 4:
        return None
    return int.from_bytes(raw[:4], byteorder="little")


# ---- public API ----

def get_location_paths(pnp_device_id: str) -> Optional[list[str]]:
    """Get the location paths for a PNP device. Returns list of raw path
    strings (e.g. ['ACPI(_SB_)#ACPI(PCI0)#...', 'PCIROOT(0)#PCI(1C05)#...'])
    or None if the property doesn't exist. Caller formats via
    core.windows.common.format_acpi_path / format_pci_path."""
    raw = _get_devnode_property(pnp_device_id, _LOCATION_PATHS)
    if raw is None:
        return None
    return _decode_string_list(raw)


def fetch_pcie_info(pnp_device_id: str) -> Optional[tuple[Optional[int], Optional[int]]]:
    """Fetch PCIe link speed (gen) and width for a PNP device.
    Returns (speed, width) where either may be None if that property is
    absent. Returns None only if both lookups fail."""
    speed_raw = _get_devnode_property(pnp_device_id, _PCIE_LINK_SPEED)
    width_raw = _get_devnode_property(pnp_device_id, _PCIE_LINK_WIDTH)
    speed = _decode_uint32(speed_raw) if speed_raw is not None else None
    width = _decode_uint32(width_raw) if width_raw is not None else None
    if speed is None and width is None:
        return None
    return (speed, width)


def get_bus_number(pnp_device_id: str) -> Optional[str]:
    """Get the bus number for a PNP device as a string, or None."""
    raw = _get_devnode_property(pnp_device_id, _BUS_NUMBER)
    if raw is None:
        return None
    val = _decode_uint32(raw)
    return str(val) if val is not None else None


def get_device_address(pnp_device_id: str) -> Optional[str]:
    """Get the device address for a PNP device as a string, or None."""
    raw = _get_devnode_property(pnp_device_id, _DEVICE_ADDRESS)
    if raw is None:
        return None
    val = _decode_uint32(raw)
    return str(val) if val is not None else None


def fetch_device_properties(
    pnp_device_id: str,
) -> tuple[Optional[list[str]], Optional[str], Optional[str]]:
    """Fetch location paths, bus number, and device address in one call."""
    return (
        get_location_paths(pnp_device_id),
        get_bus_number(pnp_device_id),
        get_device_address(pnp_device_id),
    )
