#include "gpu_info.h"
#include <cstdio>
#include <windows.h>
#include <string>

typedef int (*get_gpu_info_ptr)(WinGPUProperties *, int);

int main() {
    // Try multiple paths to find the DLL:
    // 1. Current directory
    // 2. Relative to where it's built (cmake-build-debug/../bindings/device_info.dll)
    // 3. Absolute "bindings/device_info.dll" from project root
    
    HMODULE hLib = LoadLibraryA("bindings/device_info.dll");
    if (!hLib) {
        hLib = LoadLibraryA("../bindings/device_info.dll");
    }
    if (!hLib) {
        hLib = LoadLibraryA("device_info.dll");
    }

    if (!hLib) {
        DWORD err = GetLastError();
        printf("Error: Could not load device_info.dll (Error code: %lu)\n", err);
        return 1;
    }

    auto get_gpu_info_func = reinterpret_cast<get_gpu_info_ptr>(GetProcAddress(hLib, "get_gpu_info"));
    if (!get_gpu_info_func) {
        printf("Error: Could not find get_gpu_info in device_info.dll\n");
        FreeLibrary(hLib);
        return 1;
    }

    constexpr int MAX_GPUS = 8;
    WinGPUProperties gpus[MAX_GPUS] = {};

    int count = get_gpu_info_func(gpus, MAX_GPUS);
    if (count < 0) {
        printf("Error: get_gpu_info() failed\n");
        FreeLibrary(hLib);
        return 1;
    }

    printf("Found %d GPU(s):\n\n", count);
    for (int i = 0; i < count; ++i) {
        const auto &g = gpus[i];
        printf("GPU %d:\n", i);
        printf("  Name:             %s\n", g.name);
        printf("  Manufacturer:     %s\n", g.manufacturer);
        printf("  Vendor ID:        0x%04X\n", g.vendor_id);
        printf("  Device ID:        0x%04X\n", g.device_id);
        printf("  Subsystem Vendor: 0x%04X\n", g.subsystem_vendor_id);
        printf("  Subsystem Device: 0x%04X\n", g.subsystem_device_id);
        printf("  VRAM:             %llu MB\n", g.vram_mb);
        printf("  PCIe Gen:         %d\n", g.pcie_gen);
        printf("  PCIe Width:       x%d\n", g.pcie_width);
        if (g.acpi_path[0]) printf("  ACPI Path:        %s\n", g.acpi_path);
        if (g.pci_path[0])  printf("  PCI Path:         %s\n", g.pci_path);
        printf("\n");
    }

    FreeLibrary(hLib);
    return 0;
}
