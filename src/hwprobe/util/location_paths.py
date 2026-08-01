from ctypes import (
    Structure,
    WinDLL,
    byref,
    c_buffer,
    c_char,
    c_ulong,
    c_ushort,
    c_wchar_p,
    sizeof,
)
from typing import Optional

cfgmgr = WinDLL("cfgmgr32.dll")

# DEVPKEY definitions
location_paths_key = [
    "location_paths",
    0xA45C254E,
    0xDF1C,
    0x4EFD,
    [0x80, 0x20, 0x67, 0xD1, 0x46, 0xA8, 0x50, 0xE0],
    37,
]

bus_number_key = [
    "bus_number",
    0xA45C254E,
    0xDF1C,
    0x4EFD,
    [0x80, 0x20, 0x67, 0xD1, 0x46, 0xA8, 0x50, 0xE0],
    23,
]

device_address_key = [
    "device_address",
    0xA45C254E,
    0xDF1C,
    0x4EFD,
    [0x80, 0x20, 0x67, 0xD1, 0x46, 0xA8, 0x50, 0xE0],
    30,
]

pcie_link_speed_key = [
    "current_link_speed",
    0x3AB22E31,
    0x8264,
    0x4B4E,
    [0x9A, 0xF5, 0xA8, 0xD2, 0xD8, 0xE3, 0x3E, 0x62],
    9,
]

pcie_link_width_key = [
    "current_link_width",
    0x3AB22E31,
    0x8264,
    0x4B4E,
    [0x9A, 0xF5, 0xA8, 0xD2, 0xD8, 0xE3, 0x3E, 0x62],
    10,
]


class GUID(Structure):
    """
    Source: https://github.com/tpn/winsdk-10/blob/master/Include/10.0.10240.0/shared/guiddef.h#L22-L26
    """

    _fields_ = [
        ("Data1", c_ulong),
        ("Data2", c_ushort),
        ("Data3", c_ushort),
        ("Data4", c_char * 8),
    ]


class DEVPROPKEY(Structure):
    """
    Source: https://github.com/tpn/winsdk-10/blob/master/Include/10.0.10240.0/um/devpropdef.h#L118-L124
    """

    _fields_ = [("fmtid", GUID), ("pid", c_ulong)]


def get_device_instance(pnp_device_id: str) -> c_ulong:
    """
    Get the device node instance (dnDevInst) from a PNP Device ID.

    Args:
        pnp_device_id: The PNP Device ID string (e.g., "PCI\\VEN_8086&DEV_9A09&...")

    Returns:
        Device node instance handle, or None if not found
    """
    dev_node = c_ulong()

    result = cfgmgr.CM_Locate_DevNodeW(
        byref(dev_node),
        c_wchar_p(pnp_device_id),
        c_ulong(0),  # CM_LOCATE_DEVNODE_NORMAL
    )

    if result != 0:  # CR_SUCCESS
        return None

    return dev_node


def CM_Get_DevNode_PropertyW(
    dnDevInst=c_ulong(),
    propKey=None,
    propType=c_ulong(),
    propBuff=None,
    propBuffSize=c_ulong(),
):
    if propKey is None:
        return None

    status = cfgmgr.CM_Get_DevNode_PropertyW(
        dnDevInst,
        byref(propKey),
        byref(propType),
        propBuff,
        byref(propBuffSize),
        c_ulong(0),
    )

    if status == 0x02:  # Ran out of memory
        return None

    """
        Buffer is just barely not big enough - try again with a larger buffer
    """
    if status == 0x1A or propBuff is None:
        return CM_Get_DevNode_PropertyW(
            dnDevInst,
            propKey,
            propType,
            propBuff=c_buffer(b"", sizeof(c_ulong) * propBuffSize.value),
            propBuffSize=propBuffSize,
        )

    return (propType, propBuff, propBuffSize)


def decode_location_paths(raw_bytes: bytes) -> list[str]:
    """
    Decode the raw location paths bytes into a list of strings.

    Args:
        raw_bytes: The raw bytes returned from CM_Get_DevNode_PropertyW

    Returns:
        List of location path strings
    """
    text = raw_bytes.decode("utf-16-le", errors="ignore")

    paths = [p for p in text.split("\x00") if p]

    return paths


def decode_uint32(raw_bytes: bytes) -> Optional[int]:
    """
    Decode a 32-bit unsigned integer from raw bytes.

    Args:
        raw_bytes: The raw bytes returned from CM_Get_DevNode_PropertyW

    Returns:
        Integer value, or None if decoding fails
    """
    try:
        return int.from_bytes(raw_bytes[:4], byteorder="little")
    except Exception:
        return None


def _fetch_property(pnp_device_id: str, key_def: list):  # type: ignore[type-arg]
    """
    Generic property fetcher using CM_Get_DevNode_PropertyW.

    Args:
        pnp_device_id: The PNP Device ID string
        key_def: List containing [name, Data1, Data2, Data3, Data4_list, pid]

    Returns:
        Tuple of (propType, buffer, propBuffSize) or None
    """
    mGUID = GUID(
        Data1=c_ulong(key_def[1]),
        Data2=c_ushort(key_def[2]),
        Data3=c_ushort(key_def[3]),
        Data4=bytes(key_def[4]),
    )

    dpKey = DEVPROPKEY(fmtid=mGUID, pid=c_ulong(key_def[5]))

    dnDevInst = get_device_instance(pnp_device_id)

    if dnDevInst is None:
        return None

    return CM_Get_DevNode_PropertyW(dnDevInst, dpKey)


def get_location_paths(pnp_device_id: str) -> Optional[list[str]]:
    """
    Get the location paths for a PNP device.

    Args:
        pnp_device_id: The PNP Device ID string

    Returns:
        List of location path strings, or None if not found
    """
    result = _fetch_property(pnp_device_id, location_paths_key)

    if result is None:
        return None

    raw_bytes = result[1].raw
    return decode_location_paths(raw_bytes)


def get_bus_number(pnp_device_id: str) -> Optional[str]:
    """
    Get the bus number for a PNP device.

    Args:
        pnp_device_id: The PNP Device ID string

    Returns:
        Bus number as string, or None if not found
    """
    result = _fetch_property(pnp_device_id, bus_number_key)

    if result is None:
        return None

    raw_bytes = result[1].raw
    value = decode_uint32(raw_bytes)
    return str(value) if value is not None else None


def get_device_address(pnp_device_id: str) -> Optional[str]:
    """
    Get the device address for a PNP device.

    Args:
        pnp_device_id: The PNP Device ID string

    Returns:
        Device address as string, or None if not found
    """
    result = _fetch_property(pnp_device_id, device_address_key)

    if result is None:
        return None

    raw_bytes = result[1].raw
    value = decode_uint32(raw_bytes)
    return str(value) if value is not None else None


def get_pcie_link_speed(pnp_device_id: str) -> Optional[int]:
    result = _fetch_property(pnp_device_id, pcie_link_speed_key)

    if result is None:
        return None
    raw_bytes = result[1].raw
    return decode_uint32(raw_bytes)


def get_pcie_link_width(pnp_device_id: str) -> Optional[int]:
    result = _fetch_property(pnp_device_id, pcie_link_width_key)
    if result is None:
        return None
    raw_bytes = result[1].raw
    return decode_uint32(raw_bytes)


def fetch_device_properties(
    pnp_device_id: str,
) -> tuple[Optional[list[str]], Optional[str], Optional[str]]:
    """
    Fetch location paths, bus number, and device address in one call.

    Args:
        pnp_device_id: The PNP Device ID string

    Returns:
        Tuple of (location_paths, bus_number, device_address)
    """
    return (
        get_location_paths(pnp_device_id),
        get_bus_number(pnp_device_id),
        get_device_address(pnp_device_id),
    )


def fetch_pcie_info(pnp_device_id: str) -> Optional[tuple[Optional[int], Optional[int]]]:
    """
    Fetch PCIe link speed and width for a PNP device.

    Args:
        pnp_device_id: The PNP Device ID string
    """
    speed = get_pcie_link_speed(pnp_device_id)
    width = get_pcie_link_width(pnp_device_id)

    if speed is None and width is None:
        return None

    return (speed, width)
