"""
wmi.py  -  Python ctypes binding for the WMI wrapper in wmi.dll.

Public API:
    from hwprobe.interops.win.bindings.wmi import get_wmi_data
    rows = get_wmi_data("Win32_PhysicalMemory",
                        ["BankLabel", "Capacity", "Manufacturer"],
                        namespace=r"ROOT\\CIMV2")
    for row in rows:
        print(row["BankLabel"], row["Capacity"])

Returns one dict per WMI row, keyed by the requested field names. Missing or
null properties come back as empty strings. Raises RuntimeError if the C++
side returns -1 (COM/WMI failure).

Source: interops/win/include/wmi.h and interops/win/src/wmi.cpp.
"""

import ctypes
import pathlib

# Mirror the C caps. Must match wmi.h exactly — these are the ABI.
WMI_MAX_FIELDS = 16
WMI_FIELD_LEN = 512
WMI_MAX_ROWS = 64

_HERE = pathlib.Path(__file__).parent
_LIB_PATH = _HERE / "wmi.dll"

if not _LIB_PATH.exists():
    raise FileNotFoundError(
        f"wmi.dll not found at {_LIB_PATH}.\n"
        f"Build the project first:  cmake -S { _HERE.parent } -B build && cmake --build build --config Release"
    )

_lib = ctypes.WinDLL(str(_LIB_PATH))


# ---- mirror the C struct ----

# ctypes: a fixed 2D char array. Field order matches WmiRow in wmi.h.
class _WmiRow(ctypes.Structure):
    _fields_ = [
        ("values", (ctypes.c_char * WMI_FIELD_LEN) * WMI_MAX_FIELDS),
    ]


# ---- function signature ----
_lib.get_wmi_data.restype = ctypes.c_int
_lib.get_wmi_data.argtypes = [
    ctypes.c_char_p,                       # wmi_class
    ctypes.POINTER(ctypes.c_char_p),       # fields (array of c_char_p)
    ctypes.c_int,                          # field_count
    ctypes.c_char_p,                       # namespace_str
    ctypes.POINTER(_WmiRow),               # out
    ctypes.c_int,                          # max_rows
]


# ---- public API ----

def get_wmi_data(
    wmi_class: str,
    fields: list[str],
    namespace: str = r"ROOT\CIMV2",
) -> list[dict[str, str]]:
    """
    Run `SELECT <fields> FROM <wmi_class>` against `namespace` via the C++ WMI
    wrapper and return one dict per row, keyed by `fields` in order.

    Args:
        wmi_class: WMI class name, e.g. "Win32_PhysicalMemory".
        fields:    Ordered list of property names to select. Max 16.
        namespace: WMI namespace, e.g. r"ROOT\\CIMV2" or
                   r"ROOT\\Microsoft\\Windows\\Storage". Defaults to CIMV2.

    Returns:
        list[dict[str, str]]: one entry per row. Missing/null properties are
        empty strings. Empty list means the query succeeded but returned no
        rows.

    Raises:
        RuntimeError: the C++ side returned -1 (COM init / ConnectServer /
                      ExecQuery failure).
        ValueError:   too many fields requested.
    """
    if len(fields) > WMI_MAX_FIELDS:
        raise ValueError(f"too many fields: {len(fields)} > WMI_MAX_FIELDS={WMI_MAX_FIELDS}")
    if not fields:
        return []

    class_b = wmi_class.encode("utf-8")
    ns_b = namespace.encode("utf-8")
    fields_b = (ctypes.c_char_p * len(fields))(*[f.encode("utf-8") for f in fields])

    buf = (_WmiRow * WMI_MAX_ROWS)()
    count = _lib.get_wmi_data(class_b, fields_b, len(fields), ns_b, buf, WMI_MAX_ROWS)
    if count < 0:
        raise RuntimeError("get_wmi_data() failed (C library returned -1)")

    result = []
    for i in range(count):
        row = buf[i]
        decoded = {}
        for j, name in enumerate(fields):
            raw = row.values[j]
            # raw is c_char_Array; .value stops at the first NUL.
            decoded[name] = raw.value.decode("utf-8", errors="replace")
        result.append(decoded)
    return result


# ---- quick self-check ----
# Run with:  python -m hwprobe.interops.win.bindings.wmi
if __name__ == "__main__":
    rows = get_wmi_data("Win32_Processor", ["Name", "Manufacturer"])
    print(f"Found {len(rows)} CPU(s):\n")
    for idx, r in enumerate(rows):
        print(f"CPU {idx}:")
        for k, v in r.items():
            print(f"  {k}: {v}")
        print()
