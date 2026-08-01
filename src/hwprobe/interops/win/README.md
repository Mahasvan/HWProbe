# WinWmi (`interops/win/`)

New WMI wrapper binding, intended to replace the legacy `GetWmiInfo` text-format
export in `hw_helper.dll` (now in `interops/win_old/`). Once `core/windows/`
consumers are migrated, the old `win_old/` directory can be deleted (see
`windows-rewrite-llm-plan.md` §5).

## What it exports

One C++ function, one Python function.

```c
// include/wmi.h
int get_wmi_data(const char *wmi_class,
                 const char *const *fields, int field_count,
                 const char *namespace_str,
                 WmiRow *out, int max_rows);
```

```python
# bindings/wmi.py
def get_wmi_data(
    wmi_class: str,
    fields: list[str],
    namespace: str = r"ROOT\CIMV2",
) -> list[dict[str, str]]: ...
```

Each row comes back as a `dict` keyed by the requested field names, in order.
No `|`/`=`/`\n` delimiter parsing — each field is its own fixed UTF-8 buffer on
the C side. Missing/null properties are empty strings.

## Why this exists

The legacy `GetWmiInfo` returns pipe-delimited text that breaks when a value
contains `|`, `=`, or `\n` (PNPDeviceID paths do). It is also `void` — failure
is indistinguishable from "no rows". This binding fixes both: structured rows
and a `-1` error return.

## Requirements

- Windows 10+
- Visual Studio 2019+ / MSVC Build Tools (C++17)
- CMake 3.21+
- Windows SDK (for COM/WMI headers: `ole32`, `oleaut32`, `wbemuuid`)

## Build

```sh
cmake -S . -B build
cmake --build build --config Release
```

Outputs:

- `bindings/device_info.dll` — loaded by `bindings/wmi.py`.
- `build/Release/WinWmiTest.exe` — standalone CLI self-test.

## Run

C++ self-test (queries `Win32_Processor`):

```sh
.\build\Release\WinWmiTest.exe
```

Python self-check (same query, via ctypes):

```sh
python -m hwprobe.interops.win.bindings.wmi
```

Programmatic use (the way `core/windows/*.py` will call it once migrated):

```python
from hwprobe.interops.win.bindings.wmi import get_wmi_data

rows = get_wmi_data(
    "MSFT_PhysicalDisk",
    ["FriendlyName", "MediaType", "BusType", "Size", "Manufacturer", "Model"],
    namespace=r"ROOT\Microsoft\Windows\Storage",
)
for r in rows:
    print(r["FriendlyName"], r["Size"])
```

## ABI caps

Defined in `include/wmi.h`, mirrored in `bindings/wmi.py`:

| Cap | Value | Why |
|-----|-------|-----|
| `WMI_MAX_FIELDS` | 16 | Max fields any hwprobe query uses today is 9 (`Win32_PhysicalMemory`). |
| `WMI_FIELD_LEN` | 512 | Covers PNPDeviceID paths and uint64 string forms. |
| `WMI_MAX_ROWS` | 64 | Covers memory modules, disks, NICs on any realistic machine. |

Raising any cap is a recompile on both sides — the struct is the ABI. No
runtime resizing.

## Trust boundary

`wmi_class`, `fields`, `namespace` are WMI identifiers, not free text. They
come from hardcoded literals in `core/windows/*.py`, never from end users. The
C++ side builds `SELECT f1,f2,... FROM <class>` with no escaping. If a future
caller ever passes user-supplied strings here, that caller must validate them —
do not push escaping into the C++ layer.

## Status / scope

- **In scope (this directory):** the WMI wrapper itself.
- **Out of scope (separate bindings, later):** audio (MMDevice), network (IP
  Helper + SetupAPI), display (SetupAPI + EDID), baseboard (SMBIOS). These do
  not go through WMI and are not served by this binding.
- **Not yet wired:** no `core/windows/*.py` consumer imports this yet, per the
  rewrite plan. `memory.py` and `storage.py` are the first two consumers once
  the greenlight is given.
