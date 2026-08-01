# WinDeviceInfo (`interops/win/`)

Two native bindings, each its own DLL, each its own Python ctypes module:

| DLL | C++ export | Python binding | What it does |
|-----|-----------|----------------|--------------|
| `gpu_info.dll` | `get_gpu_info` | `bindings/gpu_info.py` | GPU enumeration via DXGI + SetupAPI (name, vendor/device IDs, VRAM, ACPI/PCI paths, PCIe gen/width). |
| `wmi.dll` | `get_wmi_data` | `bindings/wmi.py` | Generic WMI wrapper (COM + WbemLocator). Takes a class name + field list + namespace, returns one dict per row. |

Both DLLs land in `bindings/` next to their Python modules. The GPU binding is
the pre-existing one moved here from `win_old/`; the WMI binding is new and
replaces the legacy `GetWmiInfo` text-format export in `hw_helper.dll` (now in
`interops/win_old/`). Once `core/windows/` consumers are migrated, `win_old/`
can be deleted (see `windows-rewrite-llm-plan.md` §5).

## Why two DLLs

Different link dependencies, different APIs, no shared code:
- GPU: `dxgi`, `setupapi`, `cfgmgr32`, `advapi32`.
- WMI: `ole32`, `oleaut32`, `wbemuuid` (COM).

Keeping them separate means a WMI-only consumer doesn't pull DXGI into its
process, and vice versa. Each Python module loads only the DLL it needs.

## Requirements

- Windows 10+
- Visual Studio 2019+ / MSVC Build Tools (C++17) — or mingw-w64 (CI uses g++)
- CMake 3.21+
- Windows SDK (DXGI, SetupAPI, COM/WMI headers)

## Build

```sh
cmake -S . -B build
cmake --build build --config Release
```

Outputs:

- `bindings/gpu_info.dll` — loaded by `bindings/gpu_info.py`.
- `bindings/wmi.dll` — loaded by `bindings/wmi.py`.
- `build/Release/WinDeviceInfo.exe` — standalone CLI self-test for both.

## Run

C++ self-test (loads both DLLs, queries GPU + `Win32_Processor`):

```sh
.\build\Release\WinDeviceInfo.exe
```

Python self-checks:

```sh
python -m hwprobe.interops.win.bindings.gpu_info   # GPU
python -m hwprobe.interops.win.bindings.wmi        # WMI (Win32_Processor)
python -m hwprobe.interops.win.bindings.verify_wmi # integration self-check
```

Programmatic use (the way `core/windows/*.py` calls them):

```python
# GPU
from hwprobe.interops.win.bindings.gpu_info import get_gpu_info
for g in get_gpu_info():
    print(g.name, f"0x{g.vendor_id:04X}", g.vram_mb)

# WMI
from hwprobe.interops.win.bindings.wmi import get_wmi_data
rows = get_wmi_data(
    "MSFT_PhysicalDisk",
    ["FriendlyName", "MediaType", "BusType", "Size", "Manufacturer", "Model"],
    namespace=r"ROOT\Microsoft\Windows\Storage",
)
for r in rows:
    print(r["FriendlyName"], r["Size"])
```

## WMI ABI caps

Defined in `include/wmi.h`, mirrored in `bindings/wmi.py`:

| Cap | Value | Why |
|-----|-------|-----|
| `WMI_MAX_FIELDS` | 16 | Max fields any hwprobe query uses today is 9 (`Win32_PhysicalMemory`). |
| `WMI_FIELD_LEN` | 512 | Covers PNPDeviceID paths and uint64 string forms. |
| `WMI_MAX_ROWS` | 64 | Covers memory modules, disks, NICs on any realistic machine. |

Raising any cap is a recompile on both sides — the struct is the ABI. No
runtime resizing.

## Trust boundary (WMI)

`wmi_class`, `fields`, `namespace` are WMI identifiers, not free text. They
come from hardcoded literals in `core/windows/*.py`, never from end users. The
C++ side builds `SELECT f1,f2,... FROM <class>` with no escaping. If a future
caller ever passes user-supplied strings here, that caller must validate them —
do not push escaping into the C++ layer.

## Status / scope

- **In scope (this directory):** GPU binding (DXGI/SetupAPI) + WMI wrapper.
- **Out of scope (separate bindings, later):** audio (MMDevice), network (IP
  Helper + SetupAPI), display (SetupAPI + EDID), baseboard (SMBIOS). These do
  not go through WMI and are not served by the WMI binding.
- **Not yet wired:** no `core/windows/*.py` consumer imports the WMI binding
  yet, per the rewrite plan. `memory.py` and `storage.py` are the first two
  consumers once the greenlight is given. The GPU binding is already wired into
  `core/windows/graphics.py`.
