# WinDeviceInfo (`interops/win/`)

Full disclosure: A big part of this C++ connector was written by Claude.
If you are someone with more know-how, and find lapses in this code, we'd be more than happy to welcome Pull Requests.

---

Windows interop with C++ consists of three native bindings, each its own DLL, each its own Python ctypes module:

| DLL | C++ exports | Python binding | What it does |
|-----|-------------|----------------|--------------|
| `gpu_info.dll` | `get_gpu_info` | `bindings/gpu_info.py` | GPU enumeration via DXGI + SetupAPI (name, vendor/device/subsystem IDs, dedicated VRAM, PNP device ID, registry VRAM fallback for >4GB cards). |
| `wmi.dll` | `get_wmi_data` | `bindings/wmi.py` | Generic WMI wrapper (COM + WbemLocator). Takes a class name + field list + namespace, returns one dict per row. |
| `display_info.dll` | `get_monitor_devices`, `get_display_connectors`, `get_gpu_for_display`, `get_edid` | `bindings/display_info.py` | Display enumeration: user32 monitors (resolution/refresh), CCD connectors (output technology + display path), DXGI output→adapter GPU match, SetupAPI + registry EDID lookup. |

All three DLLs land in `bindings/` next to their Python modules. The GPU
binding is the pre-existing one moved here from `win_old/`; the WMI and
display bindings are new and replace legacy `hw_helper.dll` exports (now in
`interops/win_old/`). Once `core/windows/` consumers are fully migrated,
`win_old/` can be deleted (see `windows-rewrite-llm-plan.md` §5).

## Why three DLLs

Different link dependencies, different APIs, no shared code:
- GPU: `dxgi`, `setupapi`, `advapi32`.
- WMI: `ole32`, `oleaut32`, `wbemuuid` (COM).
- Display: `dxgi`, `setupapi`, `advapi32`, `user32`.

Keeping them separate means a WMI-only consumer doesn't pull DXGI into its
process, a GPU-only consumer doesn't pull COM, and so on. Each Python module
loads only the DLL it needs.

## Requirements

- Windows 10+
- Visual Studio 2019+ / MSVC Build Tools (C++17) — or mingw-w64 (CI uses g++)
- CMake 3.21+
- Windows SDK (DXGI, SetupAPI, COM/WMI, user32 headers)

## Build

```sh
cmake -S . -B build
cmake --build build --config Release
```

Outputs:

- `bindings/gpu_info.dll` — loaded by `bindings/gpu_info.py`.
- `bindings/wmi.dll` — loaded by `bindings/wmi.py`.
- `bindings/display_info.dll` — loaded by `bindings/display_info.py`.
- `build/Release/WinDeviceInfo.exe` — standalone CLI self-test for all three.

## Run

C++ self-test (loads all three DLLs at runtime, queries GPU + `Win32_Processor`
+ monitors/connectors/GPU-match/EDID):

```sh
.\build\Release\WinDeviceInfo.exe
```

Python self-checks (each module has a `__main__` block):

```sh
python -m hwprobe.interops.win.bindings.gpu_info       # GPU
python -m hwprobe.interops.win.bindings.wmi            # WMI (Win32_Processor)
python -m hwprobe.interops.win.bindings.display_info   # monitors + connectors + GPU + EDID
```

Programmatic use (the way `core/windows/*.py` calls them):

```python
# GPU
from hwprobe.interops.win.bindings.gpu_info import get_gpu_info
for g in get_gpu_info():
    print(g.name, f"0x{g.vendor_id:04X}", g.dedicated_video_memory_bytes)

# WMI
from hwprobe.interops.win.bindings.wmi import get_wmi_data
rows = get_wmi_data(
    "MSFT_PhysicalDisk",
    ["FriendlyName", "MediaType", "BusType", "Size", "Manufacturer", "Model"],
    namespace=r"ROOT\Microsoft\Windows\Storage",
)
for r in rows:
    print(r["FriendlyName"], r["Size"])

# Display
from hwprobe.interops.win.bindings.display_info import (
    get_monitor_devices, get_display_connectors, get_gpu_for_display, get_edid,
)
for m in get_monitor_devices():
    print(m.device_id, m.pnp_device_id, f"{m.width}x{m.height}@{m.refresh_rate}")
    print("  GPU:", get_gpu_for_display(m.device_id))
    edid = get_edid(m.pnp_device_id)   # matches on pnp_device_id, not the CCD display path
    if edid:
        print(f"  EDID: {len(edid)} bytes")
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

## EDID lookup key

`get_edid` matches on the monitor's **PNP device ID** (e.g.
`MONITOR\SAMxxxx\{...}`), the same string `get_monitor_devices` writes into
`MonitorDevice.pnp_device_id`. It does **not** match on the CCD display path
(`\\?\DISPLAY#...`) returned by `get_display_connectors` — passing that will
return "not found". The Python and C++ self-tests both call it with
`pnp_device_id`.

## Status / scope

- **In scope (this directory):** GPU (DXGI/SetupAPI), WMI wrapper, display
  (user32 + CCD + DXGI + SetupAPI/EDID).
- **Wired into `core/windows/`:** `graphics.py` (GPU), `cpu.py`,
  `memory.py`, `storage.py`, `network.py` (WMI), `display.py` (display).
- **Out of scope (separate bindings, later):** audio (MMDevice), baseboard
  (SMBIOS). These do not go through WMI and are not served by these bindings.
- **Legacy:** `interops/win_old/` still ships `hw_helper.dll` for consumers
  not yet migrated; delete once the migration is complete.
