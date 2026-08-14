// Standalone CLI self-test for all bindings in interops/win/:
//   gpu_info.dll      -> get_gpu_info                       (DXGI + SetupAPI)
//   wmi.dll           -> get_wmi_data                       (COM + WbemLocator)
//   display_info.dll  -> get_monitor_devices,
//                       get_display_connectors,
//                       get_gpu_for_display,
//                       get_edid                            (user32 + CCD + DXGI + SetupAPI)
//
// Loads each DLL at runtime (same path the Python bindings use) so we exercise
// the real ABI without needing matching import libs. Mirrors the ctypes calls
// in bindings/*.py — if a signature drifts here, it has drifted for Python too.

#include "gpu_info.h"
#include "wmi.h"
#include "display_info.h"

#include <windows.h>
#include <cstdio>
#include <cstring>

// ---- function pointer types matching the C exports ----

typedef int (*get_gpu_info_ptr)(WinGPURaw *, int);
typedef int (*get_wmi_data_ptr)(const char *, const char *const *, int,
                                const char *, WmiRow *, int);
typedef int (*get_monitor_devices_ptr)(MonitorDevice *, int);
typedef int (*get_display_connectors_ptr)(ConnectorInfo *, int);
typedef int (*get_gpu_for_display_ptr)(const char *, char *, int);
typedef int (*get_edid_ptr)(const char *, unsigned char *, int);

// Load from bindings/ (CMake output dir / Python layout) then fall back to the
// exe's directory, exactly the search order the Python bindings rely on.
static HMODULE _load(const char *name) {
    char path[128];
    std::snprintf(path, sizeof(path), "bindings/%s", name);
    HMODULE h = LoadLibraryA(path);
    if (!h) h = LoadLibraryA(name);
    return h;
}

// =====================================================================
// gpu_info.dll
// =====================================================================

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

// =====================================================================
// wmi.dll
// =====================================================================

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

    // Negative cases: a bogus class or field must fail (-1), not silently
    // return 0 rows. The Python binding raises RuntimeError on -1.
    const char *one_field[] = {"Name"};
    const char *bogus_field[] = {"NoSuchProperty"};
    int bad_class = fn("Win32_NoSuchClass", one_field, 1, "ROOT\\CIMV2", rows, WMI_MAX_ROWS);
    int bad_field = fn("Win32_Processor", bogus_field, 1, "ROOT\\CIMV2", rows, WMI_MAX_ROWS);
    if (bad_class >= 0 || bad_field >= 0) {
        printf("[wmi] bogus class/field query returned %d/%d rows, expected -1\n",
               bad_class, bad_field);
        FreeLibrary(hLib);
        return 1;
    }

    FreeLibrary(hLib);
    return 0;
}

// =====================================================================
// display_info.dll
// =====================================================================

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
        printf("[display] missing exports (mon=%d conn=%d gpu=%d edid=%d)\n",
               !!fnMonitors, !!fnConnectors, !!fnGpu, !!fnEdid);
        FreeLibrary(hLib);
        return 1;
    }

    // Monitors (user32 enumeration) — one entry per attached display.
    MonitorDevice monitors[8] = {};
    int nm = fnMonitors(monitors, 8);
    if (nm < 0) {
        printf("[display] get_monitor_devices failed\n");
        FreeLibrary(hLib);
        return 1;
    }

    // Connectors (CCD API) — matched to monitors by GDI device name below.
    ConnectorInfo connectors[8] = {};
    int nc = fnConnectors(connectors, 8);
    if (nc < 0) {
        printf("[display] get_display_connectors failed\n");
        FreeLibrary(hLib);
        return 1;
    }

    printf("[display] Found %d monitor(s), %d connector(s):\n\n", nm, nc);
    for (int i = 0; i < nm; ++i) {
        const auto &m = monitors[i];
        printf("Monitor %d:\n", i);
        printf("  DeviceID:    %s\n", m.device_id);
        printf("  PNPDeviceID: %s\n", m.pnp_device_id);
        printf("  Resolution:  %dx%d @ %d Hz\n", m.width, m.height, m.refresh_rate);

        // GPU driving this display (DXGI output -> adapter name match).
        char gpuName[256] = {};
        if (fnGpu(m.device_id, gpuName, sizeof(gpuName)) == 0) {
            printf("  GPU:         %s\n", gpuName);
        }

        // Connector info for this display (matched by GDI device name).
        // Keep the matched connector — its display_path is the EDID lookup key.
        const ConnectorInfo *matchedConn = nullptr;
        for (int j = 0; j < nc; ++j) {
            if (std::strcmp(connectors[j].display_id, m.device_id) == 0) {
                matchedConn = &connectors[j];
                printf("  Connector:   %s (tech=%d)\n",
                       matchedConn->display_path, matchedConn->output_technology);
                break;
            }
        }

        // EDID lookup key: get_edid matches against the SetupAPI device path
        // (\\?\DISPLAY#...), so the CCD display_path works. The full PNP device
        // ID (MONITOR\...) does NOT match. Fall back to the monitor ID segment
        // (e.g. SAM1234 from MONITOR\SAM1234\{...}) — also a substring of the
        // device path. Mirrors core/windows/display.py.
        const char *edidKey = nullptr;
        char segBuf[128] = {};
        if (matchedConn && matchedConn->display_path[0]) {
            edidKey = matchedConn->display_path;
        } else {
            // Extract the segment between the first and second backslash.
            const char *p = m.pnp_device_id;
            const char *first = std::strchr(p, '\\');
            if (first) {
                const char *second = std::strchr(first + 1, '\\');
                int len = second ? (int)(second - first - 1) : (int)std::strlen(first + 1);
                if (len > 0 && len < (int)sizeof(segBuf)) {
                    std::memcpy(segBuf, first + 1, len);
                    segBuf[len] = '\0';
                    edidKey = segBuf;
                }
            }
            if (!edidKey && p[0]) edidKey = p;
        }

        unsigned char edidBuf[1024] = {};
        int edidLen = fnEdid(edidKey, edidBuf, sizeof(edidBuf));
        if (edidLen > 0) {
            printf("  EDID:        %d bytes\n", edidLen);
        } else if (edidLen == 0) {
            printf("  EDID:        not found\n");
        } else {
            printf("  EDID:        lookup error\n");
        }
        printf("\n");
    }

    FreeLibrary(hLib);
    return 0;
}

// =====================================================================
// main
// =====================================================================

int main() {
    int rc_gpu = test_gpu();
    int rc_wmi = test_wmi();
    int rc_display = test_display();
    return (rc_gpu || rc_wmi || rc_display) ? 1 : 0;
}
