// Standalone CLI test for the WMI binding. Loads device_info.dll at runtime
// (same path the Python binding uses) so we exercise the real ABI.

#include "wmi.h"
#include <windows.h>
#include <cstdio>
#include <cstring>

typedef int (*get_wmi_data_ptr)(const char *, const char *const *, int,
                                const char *, WmiRow *, int);

int main() {
    HMODULE hLib = LoadLibraryA("bindings/device_info.dll");
    if (!hLib) hLib = LoadLibraryA("device_info.dll");
    if (!hLib) {
        printf("Error: could not load device_info.dll (GetLastError=%lu)\n", GetLastError());
        return 1;
    }

    auto fn = reinterpret_cast<get_wmi_data_ptr>(
        GetProcAddress(hLib, "get_wmi_data"));
    if (!fn) {
        printf("Error: get_wmi_data not exported\n");
        FreeLibrary(hLib);
        return 1;
    }

    const char *fields[] = {"Name", "Manufacturer", "NumberOfCores", "NumberOfLogicalProcessors"};
    const int field_count = sizeof(fields) / sizeof(fields[0]);

    WmiRow rows[WMI_MAX_ROWS] = {};
    int n = fn("Win32_Processor", fields, field_count, "ROOT\\CIMV2", rows, WMI_MAX_ROWS);
    if (n < 0) {
        printf("Error: get_wmi_data returned -1\n");
        FreeLibrary(hLib);
        return 1;
    }

    printf("Found %d CPU(s):\n\n", n);
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
