// Standalone CLI test for all bindings in interops/win/:
//   gpu_info.dll    -> get_gpu_info (DXGI + SetupAPI)
//   wmi.dll         -> get_wmi_data (COM + WbemLocator)
//   display_info.dll -> get_display_connectors, get_gpu_for_display, get_edid
//
// Loads each DLL at runtime (same path the Python bindings use) so we exercise
// the real ABI without needing matching import libs.

#include "gpu_info.h"
#include "wmi.h"
#include "display_info.h"
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

typedef int (*get_monitor_devices_ptr)(MonitorDevice *, int);
typedef int (*get_display_connectors_ptr)(ConnectorInfo *, int);
typedef int (*get_gpu_for_display_ptr)(const char *, char *, int);
typedef int (*get_edid_ptr)(const char *, unsigned char *, int);

static int test_display() {
    HMODULE hLib = _load("display_info.dll");
    if (!hLib) {
        printf("[display] could not load display_info.dll (GetLastError=%lu)\n", GetLastError());
        return 1;
    }

    auto fnMonitors = reinterpret_cast<get_monitor_devices_ptr>(
        GetProcAddress(hLib, "get_monitor_devices"));
    auto fnConnectors = reinterpret_cast<get_display_connectors_ptr>(
        GetProcAddress(hLib, "get_display_connectors"));
    auto fnGpu = reinterpret_cast<get_gpu_for_display_ptr>(
        GetProcAddress(hLib, "get_gpu_for_display"));
    auto fnEdid = reinterpret_cast<get_edid_ptr>(
        GetProcAddress(hLib, "get_edid"));

    if (!fnMonitors || !fnConnectors || !fnGpu || !fnEdid) {
        printf("[display] missing exports\n");
        FreeLibrary(hLib);
        return 1;
    }

    // Monitors
    MonitorDevice monitors[8] = {};
    int nm = fnMonitors(monitors, 8);
    if (nm < 0) {
        printf("[display] get_monitor_devices failed\n");
        FreeLibrary(hLib);
        return 1;
    }

    // Connectors (for matching)
    ConnectorInfo connectors[8] = {};
    int nc = fnConnectors(connectors, 8);

    printf("[display] Found %d monitor(s):\n\n", nm);
    for (int i = 0; i < nm; ++i) {
        printf("Monitor %d:\n", i);
        printf("  DeviceID:    %s\n", monitors[i].device_id);
        printf("  PNPDeviceID: %s\n", monitors[i].pnp_device_id);
        printf("  Resolution:  %dx%d @ %d Hz\n",
               monitors[i].width, monitors[i].height, monitors[i].refresh_rate);

        // GPU for this display
        char gpuName[256] = {};
        if (fnGpu(monitors[i].device_id, gpuName, sizeof(gpuName)) == 0) {
            printf("  GPU:         %s\n", gpuName);
        }

        // Connector info
        for (int j = 0; j < nc; ++j) {
            if (strcmp(connectors[j].display_id, monitors[i].device_id) == 0) {
                printf("  Connector:   %s (tech=%d)\n",
                       connectors[j].display_path, connectors[j].output_technology);

                // EDID via display path
                unsigned char edidBuf[1024] = {};
                int edidLen = fnEdid(connectors[j].display_path, edidBuf, sizeof(edidBuf));
                if (edidLen > 0) {
                    printf("  EDID:        %d bytes\n", edidLen);
                }
                break;
            }
        }
        printf("\n");
    }

    FreeLibrary(hLib);
    return 0;
}

int main() {
    int rc_gpu = test_gpu();
    int rc_wmi = test_wmi();
    int rc_display = test_display();
    return (rc_gpu || rc_wmi || rc_display) ? 1 : 0;
}
