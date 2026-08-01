# WinDeviceInfo

A Windows utility and shared library that enumerates GPU hardware via DXGI and the Windows Configuration Manager API.

The native library lives in `src/` and `include/`, and is exposed via a command-line tester (`main.cpp`).
Also powers a thin Python `ctypes` binding in `bindings/gpu_info.py`.

This is intended to be used via each hardware component's respective python interface, like `gpu_info.py`. The CLI tool
is primarily for testing and demonstration purposes, but it can be used directly if desired.

Full disclosure: A big part of this C++ connector was written by Claude.
If you are someone with more know-how, and find lapses in this code, we'd be more than happy to welcome Pull Requests.

## Requirements

- Windows 10 or newer
- Visual Studio 2019+ or MSVC Build Tools (C++17 support required)
- CMake 3.21+
- Python 3.7+ (for the `gpu_info.py` binding) - Assuming you want to compile this to use with HWProbe.
- Windows SDK (for DXGI, SetupAPI, CfgMgr32 headers)

## Build

```sh
cmake -S . -B build
cmake --build build --config Release
```

- `WinDeviceInfo.exe` (the CLI tool) is emitted to `build/Release/WinDeviceInfo.exe`.
- `device_info.dll` is copied automatically into `bindings/` for the Python binding.
- The default build type is **Release**. Pass `--config Debug` to the build command to include debug symbols.

## CLI Usage

```sh
.\build\Release\WinDeviceInfo.exe
```

The tool prints GPU info, and exits with code `0` when enumeration succeeds, or `1` if the underlying DXGI call fails.

## Python Binding

After building the project once (so that `bindings/device_info.dll` exists), you can inspect GPUs from Python:

```sh
cd bindings
python gpu_info.py
```

or programmatically:

```python
from gpu_info import get_gpu_info

for idx, gpu in enumerate(get_gpu_info()):
    print(f"GPU {idx}:")
    print(gpu)
```

On import, the script loads the colocated `device_info.dll`; ensure you rebuild the CMake project whenever you make
changes to the native code.

## What the native library does

For each GPU discovered via DXGI:

1. **Enumerates adapters** using `IDXGIFactory1::EnumAdapters1`, skipping software/virtual adapters.
2. **Resolves the PNP Device ID** by matching DXGI's VendorId/DeviceId/SubSysId against SetupAPI's display class.
3. **Parses vendor/device/subsystem IDs** from the PNP device ID string.
4. **Fetches VRAM** from DXGI's `DedicatedVideoMemory`; falls back to the registry
   (`HardwareInformation.qwMemorySize`) for cards with >4 GB where DXGI may report a capped value.
5. **Resolves ACPI and PCI paths** via `CM_Get_DevNode_PropertyW` (location paths), formatted to match the
   project's conventions (e.g. `\_SB_.PCI0.RP05.PXSX`, `PciRoot(0x0)/Pci(0x1C,0x5)/Pci(0x0,0x0)`).
6. **Fetches PCIe generation and lane width** via Configuration Manager device properties.

## Legacy bindings

The following files belong to the **old** monolithic binding approach and are kept for components that have not yet
been migrated. They are marked with `# todo: refactor to new bindings` in the consuming code. Once all components
are migrated, these files can be deleted:

```
interops/win/legacy/
    constants.py      # Win32 constants, GUIDs, status codes
    structs.py        # ctypes Structure mirrors (MONITORINFOEXA, DEVMODEA, etc.)
    signatures.py     # Loads hw_helper.dll, sets argtypes/restypes for all exports

interops/win/
    hw_helper.hpp     # Monolithic C++ header (all structs + enums)
    hw_helper.cpp     # Monolithic C++ source (GPU, audio, network, SMBIOS, WMI - all in one file)
    dll/
        hw_helper.dll # Pre-built monolithic DLL
```

Components still using the legacy bindings:

- `core/windows/audio.py`
- `core/windows/baseboard.py`
- `core/windows/display.py`
- `core/windows/memory.py`
- `core/windows/network.py`
- `core/windows/storage.py`

## Troubleshooting

- **`device_info.dll not found`**: run the CMake build so the shared library is (re)generated in `bindings/`.
- **`get_gpu_info` returns -1**: verify that DXGI is available (Windows 10+ with a display driver installed).
- **VRAM shows 0 MB**: the registry fallback may not find a matching `DriverDesc`/`DriverVersion` entry. Check that
  the GPU driver is properly installed.
- **PCIe gen/width shows 0**: the Configuration Manager property may not be exposed by all drivers. This is
  driver-dependent and not a bug in the library.
