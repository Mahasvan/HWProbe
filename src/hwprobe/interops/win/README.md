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

All three DLLs land in `bindings/` next to their Python modules.

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
    get_monitor_devices,
    get_display_connectors,
    get_gpu_for_display,
    get_edid,
)

for m in get_monitor_devices():
    print(m.device_id, m.pnp_device_id, f"{m.width}x{m.height}@{m.refresh_rate}")
    print("  GPU:", get_gpu_for_display(m.device_id))
    edid = get_edid(m.pnp_device_id.split("\\")[1])  # monitor ID segment, see "EDID lookup key" below
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

`get_edid` iterates SetupAPI monitor device interfaces and does a
case-insensitive **substring match** between the search key and each
interface's device path, which has the form
`\\?\DISPLAY#SAMxxxx#5&...#{e6f07b5f-...}`.

Two keys match that path:

1. The **CCD display path** (`\\?\DISPLAY#SAMxxxx#...`) from
   `get_display_connectors` (`ConnectorInfo.display_path`) — a prefix of the
   SetupAPI device path. This is the preferred key; `core/windows/display.py`
   uses it first.
2. The **monitor ID segment** (e.g. `SAMxxxx`) extracted from the PNP device
   ID (`MONITOR\SAMxxxx\{...}`) by splitting on `\`. This is the fallback when
   no connector matched.

The **full PNP device ID** (`MONITOR\SAMxxxx\{...}`) does **not** match —
`MONITOR\` is not a substring of `\\?\DISPLAY#...`. Do not pass it to
`get_edid`. `get_monitor_devices` writes it into `MonitorDevice.pnp_device_id`
for use as `module.acpi_path`, not as an EDID key.

## Status / scope

- **In scope (this directory):** GPU (DXGI/SetupAPI), WMI wrapper, display
  (user32 + CCD + DXGI + SetupAPI/EDID).
- **Wired into `core/windows/`:** `graphics.py` (GPU), `cpu.py`,
  `memory.py`, `storage.py`, `network.py` (WMI), `display.py` (display).
- **Out of scope (separate bindings, later):** audio (MMDevice), baseboard
  (SMBIOS). These do not go through WMI and are not served by these bindings.
  The previous `hw_helper.dll`-based implementations in `core/windows/audio.py`
  and `core/windows/baseboard.py` are currently disabled (module bodies wrapped
  in a docstring) and removed from `manager.py`; rewrite them against new
  bindings before re-enabling.
