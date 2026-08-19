# LinuxDeviceInfo

A tiny Linux utility and shared library that enumerates GPUs using DRM ioctls (vendor-specific) with a Vulkan
fallback (universal), reporting model name and VRAM without relying on external tools like `lspci` or `nvidia-smi`.

The native library lives in `src/` and `include/`, and is exposed via a command-line tester (`main.c`).
Also powers a thin Python `ctypes` binding in `bindings/gpu_info.py`.

This is intended to be used via each hardware component's respective python interface, like `gpu_info.py`. The CLI tool
is primarily for testing and demonstration purposes, but it can be used directly if desired.

Full disclosure: A big part of this C++ connector was written by Claude.
If you are someone with more know-how, and find lapses in this code, we'd be more than happy to welcome Pull Requests.

## Vendor Coverage

| Vendor     | VRAM Source                               | Notes                                   |
| ---------- | ----------------------------------------- | --------------------------------------- |
| **AMD**    | `AMDGPU_INFO_VRAM_GTT` ioctl              | Direct kernel interface                 |
| **Intel**  | `DRM_I915_QUERY_MEMORY_REGIONS` ioctl     | Intel Arc + integrated                  |
| **NVIDIA** | Nouveau DRM ioctl + Vulkan fallback       | Vulkan preferred for proprietary driver |
| **Any**    | Vulkan `VkPhysicalDeviceMemoryProperties` | Universal fallback via `libvulkan.so.1` |

## Requirements

- Linux with a populated `/sys/class/drm` (kernel 5.16+ for Intel Arc VRAM queries)
- GCC/Clang with C++17 support
- CMake 3.21+
- `libdrm` development headers (linked at build time)
- Python 3.7+ (for the `gpu_info.py` binding) - Assuming you want to compile this to use with HWProbe.
- `libvulkan.so.1` at runtime and other Vulkan-related packages

```bash
# Debian/Ubuntu
sudo apt install build-essential cmake pkg-config libdrm-dev libvulkan-dev vulkan-headers

# Fedora/RHEL
sudo dnf install gcc-c++ cmake pkgconf-pkg-config libdrm-devel vulkan-loader-devel vulkan-headers

# Arch
sudo pacman -S base-devel cmake pkgconf libdrm vulkan-headers vulkan-icd-loader
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
./build/LinuxDeviceInfo <bdf> <vendor_id>
```

Sample output:

```
Vulkan fallback: VRAM total not detected for GPU 0000:09:00.0
GPU at 0000:09:00.0:
  Name:        NVIDIA GeForce RTX 5070 Ti
  VRAM Total:  16303 MB
  VRAM Used:   2721 MB
```

The tool exits with code `0` when enumeration succeeds, or `1` if the underlying DRM/Vulkan query fails.

## Python Binding

After building the project once (so that `bindings/libdevice_info.so` exists), you can inspect GPUs from Python:

```python
from gpu_info import get_gpu_info

gpu = get_gpu_info("0000:09:00.0", 0x10DE)
print(gpu)
```

On import, the script loads the colocated `libdevice_info.so`; ensure you rebuild the CMake project whenever you make
changes to the native code.

```python
from hwprobe.core.linux.graphics import fetch_graphics_info

info = fetch_graphics_info()
for gpu in info.modules:
    print(f"{gpu.name}: {gpu.vram.capacity}{gpu.vram.unit} VRAM")
```

## Why C++ Instead of Pure Python?

1. **No external dependencies** — `lspci`, `nvidia-smi`, `rocm-smi` may not be installed
2. **Efficient VRAM detection** — DRM ioctls work for all vendors without proprietary tools
3. **Faster** — Direct kernel interface, no subprocess overhead
4. **Unified Vulkan fallback**

## Limitations

- **Intel Arc VRAM**: Requires kernel 5.16+ for `DRM_I915_QUERY_MEMORY_REGIONS`
- **Nouveau VRAM**: Requires open Nouveau driver (proprietary NVIDIA driver uses Vulkan path)

## Troubleshooting

- **`libdevice_info.so not found`**: run the CMake build so the shared library is (re)generated in `bindings/`.
- **`get_gpu_info` returns -1**: verify that `/sys/class/drm` is populated and that DRM/Vulkan drivers are installed.
- **VRAM shows 0 MB**: the Vulkan fallback requires `libvulkan.so.1` to be installed; without it, VRAM is only
  reported for vendors with a supported DRM ioctl (AMD, Intel, open-source Nouveau).
