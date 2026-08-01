// Standalone CLI test for both bindings in interops/win/:
//   gpu_info.dll    -> get_gpu_info (DXGI + SetupAPI)
//   wmi.dll         -> get_wmi_data (COM + WbemLocator)
//
// Loads each DLL at runtime (same path the Python bindings use) so we exercise
// the real ABI without needing matching import libs.

#include "gpu_info.h"
#include "wmi.h"
#include <windows.h>
#include <cstdio>
#include <cstring>

typedef int (*get_gpu_info_ptr)(WinGPURaw *, int);
typedef int (*get_wmi_data_ptr)(const char *, const char *const *, int,
                                const char *, WmiRow *, int);

static HMODULE _load(const char *name) {
    char path[128];
    std::snprintf(path, sizeof(path), "bindings/%s", name);
    HMODULE h = LoadLibraryA(path);
    if (!h) h = LoadLibraryA(name);
    return h;
}

static int test_gpu() {
    HMODULE hLib = _load("gpu_info.dll");
    if (!hLib) {
        printf("[gpu] could not load gpu_info.dll (GetLastError=%lu)\n", GetLastError());
        return 1;
    }
    auto fn = reinterpret_cast<get_gpu_info_ptr>(GetProcAddress(hLib, "get_gpu_info"));
    if (!fn) {
        printf("[gpu] get_gpu_info not exported\n");
        FreeLibrary(hLib);
        return 1;
    }

    constexpr int MAX_GPUS = 8;
    WinGPURaw gpus[MAX_GPUS] = {};
    int count = fn(gpus, MAX_GPUS);
    if (count < 0) {
        printf("[gpu] get_gpu_info() failed\n");
        FreeLibrary(hLib);
        return 1;
    }

    printf("[gpu] Found %d GPU(s):\n\n", count);
    for (int i = 0; i < count; ++i) {
        const auto &g = gpus[i];
        printf("GPU %d:\n", i);
        printf("  Name:              %s\n", g.name);
        printf("  Vendor ID:         0x%04X\n", g.vendor_id);
        printf("  Device ID:         0x%04X\n", g.device_id);
        printf("  Subsystem ID:      0x%08X\n", g.subsystem_id);
        printf("  Dedicated VRAM:    %llu bytes\n", (unsigned long long)g.dedicated_video_memory_bytes);
        if (g.pnp_device_id[0])
            printf("  PNP Device ID:     %s\n", g.pnp_device_id);
        if (g.vram_bytes > 0)
            printf("  Registry VRAM:     %llu bytes\n", (unsigned long long)g.vram_bytes);
        printf("\n");
    }

    FreeLibrary(hLib);
    return 0;
}

static int test_wmi() {
    HMODULE hLib = _load("wmi.dll");
    if (!hLib) {
        printf("[wmi] could not load wmi.dll (GetLastError=%lu)\n", GetLastError());
        return 1;
    }
    auto fn = reinterpret_cast<get_wmi_data_ptr>(GetProcAddress(hLib, "get_wmi_data"));
    if (!fn) {
        printf("[wmi] get_wmi_data not exported\n");
        FreeLibrary(hLib);
        return 1;
    }

    const char *fields[] = {"Name", "Manufacturer", "NumberOfCores", "NumberOfLogicalProcessors"};
    const int field_count = sizeof(fields) / sizeof(fields[0]);

    WmiRow rows[WMI_MAX_ROWS] = {};
    int n = fn("Win32_Processor", fields, field_count, "ROOT\\CIMV2", rows, WMI_MAX_ROWS);
    if (n < 0) {
        printf("[wmi] get_wmi_data returned -1\n");
        FreeLibrary(hLib);
        return 1;
    }

    printf("[wmi] Found %d CPU(s):\n\n", n);
    for (int i = 0; i < n; ++i) {
        printf("CPU %d:\n", i);
        for (int f = 0; f < field_count; ++f) {
            printf("  %-26s %s\n", fields[f], rows[i].values[f]);
        }
        printf("\n");
    }

    FreeLibrary(hLib);
    return 0;
}

int main() {
    int rc_gpu = test_gpu();
    int rc_wmi = test_wmi();
    return (rc_gpu || rc_wmi) ? 1 : 0;
}
