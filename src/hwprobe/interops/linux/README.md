# LinuxDeviceInfo

A tiny Linux utility and shared library that enumerates GPUs using DRM ioctls (vendor-specific) with a Vulkan
fallback (universal), reporting model name, vendor/device IDs, VRAM, PCIe generation/width, PCI slot, and driver
name without relying on external tools like `lspci` or `nvidia-smi`.

The native library lives in `src/` and `include/`, and is exposed via a command-line tester (`main.c`).
Also powers a thin Python `ctypes` binding in `bindings/gpu_info.py`.

This is intended to be used via each hardware component's respective python interface, like `gpu_info.py`. The CLI tool
is primarily for testing and demonstration purposes, but it can be used directly if desired.

Full disclosure: A big part of this C++ connector was written by Claude.
If you are someone with more know-how, and find lapses in this code, we'd be more than happy to welcome Pull Requests.

## Vendor Coverage

| Vendor | VRAM Source | Notes |
|--------|-------------|-------|
| **AMD** | `AMDGPU_INFO_VRAM_GTT` ioctl | Direct kernel interface |
| **Intel** | `DRM_I915_QUERY_MEMORY_REGIONS` ioctl | Intel Arc + integrated |
| **NVIDIA** | Nouveau DRM ioctl + Vulkan fallback | Vulkan preferred for proprietary driver |
| **Any** | Vulkan `VkPhysicalDeviceMemoryProperties` | Universal fallback via `libvulkan.so.1` |

## Requirements

- Linux with a populated `/sys/class/drm` (kernel 5.16+ for Intel Arc VRAM queries)
- GCC/Clang with C++17 support
- CMake 3.21+
- `libdrm` development headers (linked at build time)
- Python 3.7+ (for the `gpu_info.py` binding) - Assuming you want to compile this to use with HWProbe.
- `libvulkan.so.1` at runtime (optional; `dlopen`'d for the universal fallback path, no SDK headers needed to build)

```bash
# Debian/Ubuntu
sudo apt install build-essential cmake libdrm-dev

# Fedora/RHEL
sudo dnf install gcc-c++ cmake libdrm-devel

# Arch
sudo pacman -S base-devel cmake libdrm
```

## Build

```sh
cmake -S . -B build
cmake --build build
```

- `LinuxDeviceInfo` (the CLI tool) is emitted to `build/LinuxDeviceInfo`.
- `libdevice_info.so` is copied automatically into `bindings/` for the Python binding.
- The default build type is **Release**, compiled with `-g -fno-omit-frame-pointer` so native profilers (perf,
  `py-spy --native`) can still unwind and symbolize the library.

## CLI Usage

```sh
./build/LinuxDeviceInfo
```

Sample output:

```
Found 1 GPU(s):

GPU 0:
  Name:        NVIDIA GeForce RTX 5070 Ti
  Vendor ID:   0x10DE
  Device ID:   0x2C05
  PCI Slot:    0000:09:00.0
  Driver:      nvidia
  VRAM Total:  16384 MB
  VRAM Used:   0 MB
  PCIe Gen:    4
  PCIe Width:  x16
```

The tool exits with code `0` when enumeration succeeds, or `1` if the underlying DRM/Vulkan query fails.

## Python Binding

After building the project once (so that `bindings/libdevice_info.so` exists), you can inspect GPUs from Python:

```sh
cd bindings
python3 gpu_info.py
```

or programmatically:

```python
from gpu_info import get_gpu_info

for idx, gpu in enumerate(get_gpu_info()):
    print(f"GPU {idx}:")
    print(gpu)
```

On import, the script loads the colocated `libdevice_info.so`; ensure you rebuild the CMake project whenever you make
changes to the native code.

Or use the high-level API (automatic fallback to sysfs + `lspci`/`nvidia-smi`/`rocm-smi` when the native library
isn't available):

```python
from hwprobe.core.linux.graphics import fetch_graphics_info

info = fetch_graphics_info()
for gpu in info.modules:
    print(f"{gpu.name}: {gpu.vram.capacity}{gpu.vram.unit} VRAM")
```

## Why C++ Instead of Pure Python?

1. **No external dependencies** — `lspci`, `nvidia-smi`, `rocm-smi` may not be installed
2. **Vendor-neutral VRAM** — DRM ioctls work for all vendors without proprietary tools
3. **Faster** — Direct kernel interface, no subprocess overhead
4. **Unified Vulkan fallback** — When DRM doesn't provide VRAM, Vulkan fills the gap

## Limitations

- **ACPI path**: Optional, requires `firmware_node` in sysfs (not all systems)
- **Intel Arc VRAM**: Requires kernel 5.16+ for `DRM_I915_QUERY_MEMORY_REGIONS`
- **Nouveau VRAM**: Requires open Nouveau driver (proprietary NVIDIA driver uses Vulkan path)

## Troubleshooting

- **`libdevice_info.so not found`**: run the CMake build so the shared library is (re)generated in `bindings/`.
- **`get_gpu_info` returns -1**: verify that `/sys/class/drm` is populated and that DRM/Vulkan drivers are installed.
- **VRAM shows 0 MB**: the Vulkan fallback requires `libvulkan.so.1` to be installed; without it, VRAM is only
  reported for vendors with a supported DRM ioctl (AMD, Intel, open-source Nouveau).
- **PCIe gen/width shows 0**: the sysfs link-status attributes may not be exposed by all drivers. This is
  driver-dependent and not a bug in the library.

## Future Enhancements

- [ ] PCIe max capability vs. negotiated (currently only shows negotiated)
- [ ] Physical slot label (e.g., "PCIE1") from sysfs `PhySlot:` attribute
- [ ] Multi-GPU VRAM usage per-process breakdown
